//! Regression: a session's kernel must write session-local harness entries
//! (`rlm.harness.create_memory` without `global_=True`) into the directory the
//! host reads for the harness digest and refinement, `<artifact dir>/harness`.
//!
//! The kernel resolves local state from `RLM_SESSION_DIR`; when the host did
//! not pass it, every local write raised "Local harness state requires
//! `RLM_HARNESS_STATE_DIR` or `RLM_SESSION_DIR`".
#![cfg(unix)]

use std::path::PathBuf;

use pa_core::kernel::shared::{ExecuteOptions, ExecuteStatus, HostRequestHandlers};
use pa_core::refinement::{
    get_local_harness_state_dir, load_harness_state, HarnessScope, RefinementKind,
};
use pa_core::session_engine::runtime_wiring::kernel_provisioner;

/// The kernel Python with the runtime installed: `PA_CORE_KERNEL_PYTHON`, else
/// the product's kernel venv. `None` skips the test on machines without one,
/// like the other live-kernel tests.
fn kernel_python() -> Option<PathBuf> {
    if let Some(explicit) = std::env::var_os("PA_CORE_KERNEL_PYTHON") {
        return Some(PathBuf::from(explicit));
    }
    let candidate =
        PathBuf::from(std::env::var("HOME").ok()?).join(".prime/agent/kernel-venv/bin/python");
    candidate.exists().then_some(candidate)
}

#[tokio::test]
async fn local_harness_memory_lands_in_the_session_artifact_dir() {
    let Some(python) = kernel_python() else {
        eprintln!("kernel python not found; skipping live kernel test");
        return;
    };
    // This binary holds a single test, so no other thread reads the env.
    std::env::set_var("PRIME_AGENT_KERNEL_PYTHON", &python);

    let agent_dir = tempfile::tempdir().expect("agent dir");
    let artifact_dir = tempfile::tempdir().expect("artifact dir");
    let provisioner = kernel_provisioner(
        "local-state-test".to_string(),
        HostRequestHandlers::new(),
        Vec::new(),
        std::env::temp_dir(),
        agent_dir.path(),
        Some(artifact_dir.path().to_path_buf()),
        None,
        None,
        None,
        None,
    );
    let manager = provisioner.ensure(None, None).await.expect("kernel starts");

    let result = manager
        .execute(
            "rlm.harness.create_memory('local note', 'kept for this session').id",
            ExecuteOptions::default(),
        )
        .await
        .expect("execute");
    assert_eq!(result.status, ExecuteStatus::Ok, "cell: {:?}", result.error);

    let local_dir = get_local_harness_state_dir(Some(artifact_dir.path())).expect("local dir");
    let state = load_harness_state(&local_dir, HarnessScope::Local);
    let memories: Vec<(String, String)> = state.entries[&RefinementKind::Memory]
        .values()
        .map(|entry| (entry.title.clone(), entry.content.clone()))
        .collect();
    assert_eq!(
        memories,
        vec![(
            "local note".to_string(),
            "kept for this session".to_string()
        )]
    );

    provisioner.dispose(None).await;
}
