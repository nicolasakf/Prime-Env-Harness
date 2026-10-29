//! Environment python responsibility.
use super::{
    assert_resolved, bail, component, ensure_image, fs, intent_once, json, read_json,
    receipt_value, value, write_json, ActiveInstance, Arc, BTreeMap, CancellationToken, Context,
    EnvironmentLanguage, EnvironmentManager, ExecutionBackend, ExecutionPolicy, HostCallHandler,
    OperationReceipt, PathBuf, Result, SeatId, Uuid, Value,
};
use crate::Worker;
use std::sync::atomic::{AtomicBool, Ordering};

impl EnvironmentManager {
    pub(super) async fn kernel_source(&self, policy: &ExecutionPolicy) -> Result<PathBuf> {
        let path = self
            .store
            .root()
            .join("prepared")
            .join("participant-kernel-v1");
        fs::create_dir_all(&path)?;
        fs::write(
            path.join("kernel.py"),
            include_str!("../../sdk/python/kernel.py"),
        )?;
        if policy.backend == ExecutionBackend::Docker {
            ensure_image(
                EnvironmentLanguage::Python,
                &path,
                policy.preparation_timeout_seconds,
            )
            .await?;
        }
        Ok(path)
    }
}

impl ActiveInstance {
    /// Execute participant Python in its selected backend and checkpoint its namespace.
    /// # Errors
    /// Returns disabled-kernel, execution, uncertain-operation, or checkpoint errors.
    #[tracing::instrument(skip_all)]
    pub async fn execute_python(
        self: &Arc<Self>,
        code: &str,
        operation_id: &str,
        signal: CancellationToken,
    ) -> Result<Value> {
        self.execute_python_seat(&SeatId::legacy_agent(), code, operation_id, signal)
            .await
    }

    pub(super) fn python_path(&self, seat: &SeatId) -> PathBuf {
        if self.definition.manifest.protocol_version == 1 {
            self.path.clone()
        } else {
            self.path.join("seats").join(seat.as_str())
        }
    }

    /// Execute Python with a separate persisted namespace and bound host calls per seat.
    /// # Errors
    /// Returns missing-seat, disabled-kernel, uncertain-operation, and persistence errors.
    #[tracing::instrument(skip_all)]
    pub async fn execute_python_seat(
        self: &Arc<Self>,
        seat: &SeatId,
        code: &str,
        operation_id: &str,
        signal: CancellationToken,
    ) -> Result<Value> {
        self.execute_python_seat_inner(seat, code, operation_id, signal, /*host_calls*/ None)
            .await
    }

    /// Execute seat Python with host-owned observe/invoke admission.
    /// The adapter must bind the seat identity and enforce run controls and limits.
    /// Integration calls remain subject to this instance's execution policy.
    /// # Errors
    /// Returns adapter failures and the same execution/recovery errors as seat Python.
    #[tracing::instrument(skip_all)]
    pub async fn execute_python_seat_with_host(
        self: &Arc<Self>,
        seat: &SeatId,
        code: &str,
        operation_id: &str,
        signal: CancellationToken,
        host_calls: HostCallHandler,
    ) -> Result<Value> {
        self.execute_python_seat_inner(seat, code, operation_id, signal, Some(host_calls))
            .await
    }

    // One cell's lifecycle (intent, bridge, execution, aborted-cell resolution,
    // checkpoint, receipt) stays in one place so the ordering that decides whether a
    // cell is resolved or uncertain is read top to bottom.
    #[allow(clippy::too_many_lines)]
    #[tracing::instrument(skip_all)]
    async fn execute_python_seat_inner(
        self: &Arc<Self>,
        seat: &SeatId,
        code: &str,
        operation_id: &str,
        signal: CancellationToken,
        host_calls: Option<HostCallHandler>,
    ) -> Result<Value> {
        component(operation_id)?;
        let request = json!({"code":code});
        let kernel = self
            .python
            .lock()
            .await
            .get(seat)
            .cloned()
            .context("this environment does not provide Python execution")?;
        let mut kernel = kernel.lock().await;
        let path = self.python_path(seat);
        let receipts_path = path.join("python-receipts.json");
        let mut receipts: BTreeMap<String, OperationReceipt> = if receipts_path.exists() {
            read_json(&receipts_path)?
        } else {
            BTreeMap::new()
        };
        if let Some(receipt) = receipts.get(operation_id) {
            return receipt_value(receipt, &request);
        }
        assert_resolved(&path.join("python-operations"), &receipts)?;
        intent_once(
            &path
                .join("python-operations")
                .join(format!("{operation_id}.json")),
            &request,
        )?;
        let active = Arc::clone(self);
        let bound_seat = seat.clone();
        let bridge_signal = signal.clone();
        // Set once the cell issues any host call other than a read-only observe.
        let effects = Arc::new(AtomicBool::new(false));
        let bridge_effects = Arc::clone(&effects);
        let host: HostCallHandler = Arc::new(move |call| {
            let seat = bound_seat.clone();
            let active = Arc::clone(&active);
            let host_calls = host_calls.clone();
            let signal = bridge_signal.clone();
            let effects = Arc::clone(&bridge_effects);
            Box::pin(async move {
                if signal.is_cancelled() {
                    bail!("Python host call cancelled");
                }
                if call.method != "environment.observe" {
                    effects.store(true, Ordering::SeqCst);
                }
                if matches!(
                    call.method.as_str(),
                    "environment.observe" | "environment.invoke"
                ) {
                    if let Some(host) = host_calls {
                        return host(call).await;
                    }
                }
                match call.method.as_str() {
                    "environment.observe" => active.observe(&seat).await,
                    "environment.invoke" => {
                        active
                            .invoke(
                                &seat,
                                call.params["action"].as_str().context("action name")?,
                                call.params["arguments"].clone(),
                                &Uuid::new_v4().to_string(),
                                CancellationToken::new(),
                            )
                            .await
                    }
                    "integration.call" => (active.integration_handler(&seat))(call).await,
                    _ => bail!("participant kernel request is not permitted"),
                }
            })
        });
        let agent = seat.clone();
        let outcome = tokio::select! {
            () = self.shutdown.cancelled() => {
                kernel.cancel().await;
                bail!("instance is leaving; Python outcome is uncertain");
            },
            result = kernel.request("execute", &agent, request.clone(), signal, Some(&host)) => result,
        };
        let response = match outcome {
            Ok(response) => response,
            Err(error) if !effects.load(Ordering::SeqCst) => {
                // The kernel process was stopped, but the cell reached nothing the host
                // tracks beyond this seat's namespace, and the last checkpoint still
                // holds that namespace from before the cell. Restart from it and record
                // the cell as cancelled rather than blocking the seat for recovery.
                // Cells with host-visible effects stay uncertain.
                let source = self
                    .kernel_source
                    .as_ref()
                    .context("this environment does not provide Python execution")?;
                *kernel = Worker::start(
                    source,
                    &path.join("participant"),
                    EnvironmentLanguage::Python,
                    &self.instance.policy,
                    /*kernel*/ true,
                )
                .await
                .context("restarting Python after an aborted cell")?;
                let receipt = OperationReceipt {
                    request: request.clone(),
                    success: false,
                    result: json!(format!(
                        "Python cell aborted ({error:#}); variables were restored to their state before this cell"
                    )),
                    ..OperationReceipt::default()
                };
                receipts.insert(operation_id.into(), receipt.clone());
                write_json(&receipts_path, &receipts)?;
                return receipt_value(&receipt, &request);
            }
            Err(error) => return Err(error),
        };
        let checkpoint = value(
            kernel
                .request("checkpoint", seat, json!({}), self.shutdown.clone(), None)
                .await?,
        )?;
        let receipt = OperationReceipt {
            request: request.clone(),
            success: response["success"] == true,
            result: if response["success"] == true {
                json!({"execution":response["result"],"checkpoint":checkpoint})
            } else {
                response["error"].clone()
            },
            ..OperationReceipt::default()
        };
        receipts.insert(operation_id.into(), receipt.clone());
        write_json(&receipts_path, &receipts)?;
        receipt_value(&receipt, &request)
    }
}
