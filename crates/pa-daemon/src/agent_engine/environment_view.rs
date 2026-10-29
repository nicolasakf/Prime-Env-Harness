//! Opening a run's viewer: the live page of a run whose table is up, or the
//! replay page of an ended run.
//!
//! Replays are exported by the environments skill's viewer tool, so the page
//! the builder exports and the page opened here are the same file.
use std::path::Path;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use pa_environments::EnvironmentManager;
use serde_json::{json, Value};

use super::AgentEngineConfig;
use crate::environment_host::RunState;
use crate::supervisor_link::SupervisorLink;

const VIEWER_TOOL: &str =
    include_str!("../../../../skills/environments/assets/viewers/viewer_tool.py");
const VIEWER_RUNTIME: &str =
    include_str!("../../../../skills/environments/assets/viewers/viewer_runtime.js");
const EXPORT_TIMEOUT: Duration = Duration::from_secs(120);

/// What to open for one run.
pub(super) struct ViewRequest<'a> {
    pub id: &'a str,
    /// A saved viewer to use when several list the run's version.
    pub viewer: Option<&'a str>,
    /// The live perspective; absent means the table's human seat, else public.
    pub perspective: Option<Value>,
    /// The run's host session when the caller just created it.
    pub host_session: Option<&'a str>,
    pub config: &'a AgentEngineConfig,
}

/// The page for a run: live while the run is not over, the replay export once it
/// has ended. Returns `{"kind": "live" | "replay", "url": ...}`.
pub(super) async fn open_run_viewer(
    manager: &EnvironmentManager,
    link: &SupervisorLink,
    request: ViewRequest<'_>,
) -> Result<Value> {
    let path = manager.store().instance_path(request.id)?;
    let run_file = path.join("run.json");
    let ended = run_file.exists()
        && crate::environment_host::read::<RunState>(&run_file)?
            .phase
            .is_terminal();
    if ended {
        let instance = manager.store().instance(request.id)?;
        let root = path
            .parent()
            .and_then(Path::parent)
            .context("instance directory has no environments root")?;
        let opened = replay(root, &instance.definition_id, request.id, request.viewer).await;
        crate::environment_telemetry::track(
            crate::environment_telemetry::client(request.config).as_ref(),
            "environment_replay_view",
            if opened.is_ok() {
                "completed"
            } else {
                "failed"
            },
            None,
        );
        return opened;
    }
    let session = if let Some(session) = request.host_session {
        session.to_owned()
    } else {
        let host: Value = crate::environment_host::read(&path.join("host-session.json"))
            .context("this run has no live host; resume it to view it")?;
        host["activeSessionId"]
            .as_str()
            .context("this run has no live host; resume it to view it")?
            .to_owned()
    };
    let response = link
        .request(
            json!({"type":"env","activeSessionId":session,"operation":"view","parameters":{"perspective":request.perspective,"viewer":request.viewer}}),
            Duration::from_secs(180),
        )
        .await?;
    if !response.success {
        bail!(
            "live view unavailable: {}",
            response.error.unwrap_or_default()
        );
    }
    let mut live = response.data.unwrap_or(Value::Null);
    live["kind"] = json!("live");
    Ok(live)
}

/// The run's replay page, exported first when it is missing or older than a
/// saved viewer of the definition.
async fn replay(root: &Path, definition: &str, id: &str, viewer: Option<&str>) -> Result<Value> {
    let page = root
        .join("replays")
        .join(definition)
        .join(id)
        .join("index.html");
    let exported = std::fs::metadata(&page)
        .and_then(|meta| meta.modified())
        .ok();
    let viewer_changed = exported.is_none_or(|exported| {
        std::fs::read_dir(root.join("viewers").join(definition)).is_ok_and(|viewers| {
            viewers.flatten().any(|entry| {
                std::fs::metadata(entry.path().join("viewer.json"))
                    .and_then(|meta| meta.modified())
                    .is_ok_and(|modified| modified > exported)
            })
        })
    });
    if viewer_changed {
        export_replay(root, id, viewer).await?;
    }
    let encoded: String = page
        .to_string_lossy()
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' | b'/' => {
                char::from(byte).to_string()
            }
            other => format!("%{other:02X}"),
        })
        .collect();
    Ok(json!({"kind":"replay","url":format!("file://{encoded}"),"path":page}))
}

/// Run the viewer tool's `export` for one run. The tool refuses an unended run
/// or a definition without a viewer listing the run's version, which surfaces
/// as the error.
async fn export_replay(root: &Path, id: &str, viewer: Option<&str>) -> Result<()> {
    let scratch = std::env::temp_dir().join(format!(
        "prime-env-viewer-tool-{}",
        uuid::Uuid::new_v4().simple()
    ));
    std::fs::create_dir_all(&scratch)?;
    let outcome = async {
        std::fs::write(scratch.join("viewer_tool.py"), VIEWER_TOOL)?;
        std::fs::write(scratch.join("viewer_runtime.js"), VIEWER_RUNTIME)?;
        let python = std::env::var("PRIME_ENV_PYTHON").unwrap_or_else(|_| "python3".into());
        let mut command = tokio::process::Command::new(python);
        command
            .arg("-I")
            .arg(scratch.join("viewer_tool.py"))
            .arg("--root")
            .arg(root)
            .args(["export", id, "--replace"])
            .kill_on_drop(true);
        if let Some(viewer) = viewer {
            command.args(["--viewer", viewer]);
        }
        let output = tokio::time::timeout(EXPORT_TIMEOUT, command.output())
            .await
            .context("replay export timed out")??;
        let report: Value = serde_json::from_slice(&output.stdout).with_context(|| {
            format!(
                "replay export failed: {}",
                String::from_utf8_lossy(&output.stderr)
            )
        })?;
        if let Some(refused) = report["refused"].as_str() {
            bail!("{refused}");
        }
        Ok(())
    }
    .await;
    // Best effort: a leftover scratch folder is only temporary files.
    let _ = std::fs::remove_dir_all(&scratch);
    outcome
}
