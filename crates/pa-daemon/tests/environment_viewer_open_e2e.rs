#![cfg(unix)]
//! Entering a run opens its viewer: the live page while the run is in play and the
//! replay once it has ended, and nothing when no saved viewer lists its version.
#[path = "support/environment_daemon.rs"]
mod support;
use serde_json::{json, Value};
use support::start;

const ENVIRONMENT: &str = r#"class Environment:
    def initialize(self, params):
        self.count = 0
        return {}

    def describe_actions(self):
        return [{"name": "tick", "description": "Count once.", "input_schema": {"type": "object"},
                 "output_schema": {"type": "object"}, "roles": ["player"]}]

    def observe(self, seat):
        return {"count": self.count}

    def frame(self, perspective):
        return {"count": self.count}

    def handle_input(self, seat, text):
        raise ValueError("talk is disabled")

    def invoke(self, seat, action, arguments):
        self.count += 1
        return {}

    def snapshot(self):
        return {"count": self.count}

    def restore(self, snapshot):
        self.count = snapshot["count"]
        return {}

    def dispose(self):
        return {}


environment = Environment()
"#;

#[test]
fn entering_a_run_opens_its_live_viewer_and_an_ended_run_its_replay() {
    let root = tempfile::tempdir().unwrap();
    let (_supervisor, mut client) = start(root.path(), &json!({"engine":"faux","responses":[]}));
    let created = client.request(&json!({"type":"create","config":{"cwd":root.path(),"script":root.path().join("faux.json"),"sessionDir":root.path().join("agent/sessions")},"telemetryDisabled":true}));
    assert_eq!(created["success"], true, "{created}");
    let builder = created["data"]["activeSessionId"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        client.request(&json!({"type":"attach","activeSessionId":builder}))["success"],
        true
    );
    let draft = client.environment(
        &builder,
        "create",
        &json!({"description":"counter with a frame","language":"python"}),
    )["draft"]
        .as_str()
        .unwrap()
        .to_owned();
    let path = std::path::Path::new(&draft);
    let mut manifest: Value =
        serde_json::from_slice(&std::fs::read(path.join("environment.json")).unwrap()).unwrap();
    manifest["protocol_version"] = json!(2);
    manifest["roles"] = json!([{"name":"player","min_seats":1,"max_seats":1}]);
    std::fs::write(path.join("environment.json"), manifest.to_string()).unwrap();
    std::fs::write(path.join("environment.py"), ENVIRONMENT).unwrap();
    std::fs::write(path.join("checks.py"), "").unwrap();
    let policy = json!({"backend":"local"});
    client.environment(&builder, "policy", &json!({"draft":draft,"policy":policy}));
    let report = client.environment(&builder, "validate", &json!({"draft":draft}));
    assert_eq!(report["passed"], true, "{report}");
    let saved = client.environment(&builder, "save", &json!({"draft":draft,"id":"counter"}));

    let unviewed = client.environment(&builder, "enter", &json!({"id":"counter","policy":policy}));
    assert_eq!(unviewed["viewer"]["kind"], "none", "{unviewed}");

    let viewer = root.path().join("agent/environments/viewers/counter/board");
    std::fs::create_dir_all(&viewer).unwrap();
    std::fs::write(
        viewer.join("viewer.json"),
        json!({"id":"board","title":"Board","definition_id":"counter","compatible_versions":[saved["version"]],"revision":"v1","content_hash":"0","shell":true}).to_string(),
    )
    .unwrap();
    std::fs::write(
        viewer.join("index.html"),
        "<!doctype html><html><head><title>t</title></head><body>board</body></html>",
    )
    .unwrap();

    let entered = client.environment(&builder, "enter", &json!({"id":"counter","policy":policy}));
    let live = entered["viewer"]["url"].as_str().unwrap();
    assert_eq!(entered["viewer"]["kind"], "live", "{entered}");
    assert!(live.starts_with("http://127.0.0.1:"), "{live}");

    // The terminal opens the page from the readiness event it already renders.
    let ready = client.wait_event(|event| {
        event["type"] == "environment_update"
            && event["operation"] == "enter"
            && event["phase"] == "ready"
            && event["data"]["viewer"]["kind"] == "live"
    });
    assert_eq!(ready["data"]["viewer"], entered["viewer"]);

    let instance = entered["instance_id"].as_str().unwrap();
    client.environment(&builder, "stop", &json!({"id":instance}));
    let ended = client.environment(&builder, "view", &json!({"id":instance}));
    assert_eq!(ended["kind"], "replay", "{ended}");
    let page = std::fs::read_to_string(ended["path"].as_str().unwrap()).unwrap();
    assert_eq!(
        ended["url"],
        format!("file://{}", ended["path"].as_str().unwrap())
    );
    assert!(page.contains("env-viewer-page"), "{page}");
}
