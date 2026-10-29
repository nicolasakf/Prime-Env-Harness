//! Apply public host status and environment request results.
use super::{AgentView, SessionUi, Value};

/// The session the pane moves to once an environment operation is ready:
/// the table it opened, or after a leave the builder the table was opened
/// from in this TUI (`return_session`), falling back to the builder the run
/// saved, whose id may be from before that session last reopened.
/// The limits a run started with, in words, so the human sees what caps apply before
/// the first turn. `None` when the entered state carries no limits.
fn run_limits_note(limits: &Value) -> Option<String> {
    let seconds = limits["seat_turn_timeout_seconds"].as_u64()?;
    let count = |key: &str, unset: &str| {
        limits[key]
            .as_u64()
            .map_or_else(|| unset.to_owned(), |value| value.to_string())
    };
    Some(format!(
        "Run limits: operations {}; wakes per seat {}; wall clock {}; turn timeout {seconds} s; output tokens per request {}. Set them with the roster `limits` object when entering.",
        count("max_operations", "no limit"),
        count("max_wakes_per_seat", "no limit"),
        limits["max_wall_clock_seconds"]
            .as_u64()
            .map_or_else(|| "no limit".to_owned(), |value| format!("{value} s")),
        count("max_output_tokens", "provider default"),
    ))
}

fn rebind_target(data: &Value, return_session: Option<String>) -> Option<String> {
    data["session"]["activeSessionId"]
        .as_str()
        .or_else(|| data["session"]["session"]["activeSessionId"].as_str())
        .map(str::to_owned)
        .or(return_session)
        .or_else(|| data["builder_session_id"].as_str().map(str::to_owned))
}

impl SessionUi {
    pub(crate) fn apply_environment_event(&mut self, event: &Value, view: &mut AgentView) {
        if event["type"] == "environment_status" || event["type"] == "environment_seat_state" {
            self.environment_status["run"] = event["run"].clone();
        }
        // What the human is shown, and the version their submissions are bound to.
        if event["type"] == "environment_observation"
            && self.environment_profile.is_some()
            && event["view_version"].is_u64()
        {
            self.environment_status["observation"] = event["observation"].clone();
            self.environment_status["view_version"] = event["view_version"].clone();
        }
        if event["type"] == "environment_update" {
            if self.environment_profile.is_some()
                && event["phase"] == "ready"
                && event["data"].get("run").is_some()
            {
                self.environment_status = event["data"].clone();
            }
            if event["ui_origin"]
                .as_str()
                .is_some_and(|origin| self.environment_pending.as_deref() == Some(origin))
                && matches!(event["phase"].as_str(), Some("ready" | "failed"))
            {
                self.environment_pending = None;
                if view
                    .environment_panel
                    .as_ref()
                    .is_some_and(|panel| panel.pending)
                {
                    if let Some(panel) = &view.environment_panel {
                        self.track_feature_outcome(
                            panel.feature(),
                            if event["phase"] == "ready" {
                                "completed"
                            } else {
                                "failed"
                            },
                            None,
                        );
                    }
                    if event["phase"] == "ready" {
                        view.environment_panel = None;
                    } else if let Some(panel) = &mut view.environment_panel {
                        panel.fail(
                            event["error"]
                                .as_str()
                                .unwrap_or("Environment request failed")
                                .to_owned(),
                        );
                        // A refused submission was followed by the refreshed state; the
                        // next submit is bound to that, once the human has seen it.
                        panel.view_version = self.environment_status["view_version"].as_u64();
                    }
                }
                self.track_feature_outcome(
                    "environment",
                    if event["phase"] == "ready" {
                        "completed"
                    } else {
                        "failed"
                    },
                    None,
                );
                if event["phase"] == "ready" {
                    let return_session = if event["operation"] == "leave" {
                        self.environment_return_session.take()
                    } else {
                        None
                    };
                    self.pending_rebind = rebind_target(&event["data"], return_session);
                    self.plain_row(
                        &serde_json::to_string_pretty(&event["data"])
                            .unwrap_or_else(|_| event["data"].to_string()),
                        view,
                    );
                    if matches!(event["operation"].as_str(), Some("enter" | "resume")) {
                        if let Some(note) = run_limits_note(&event["data"]["roster"]["limits"]) {
                            self.note(&note, view);
                        }
                    }
                    // Entering a run shows its viewer beside the table: the live page
                    // of a run in play, the replay of an ended one.
                    if matches!(
                        event["operation"].as_str(),
                        Some("enter" | "resume" | "watch")
                    ) {
                        self.open_environment_viewer(&event["data"]["viewer"], view);
                    }
                }
            }
            self.note(
                &format!(
                    "Environment {}: {}{}{}",
                    event["operation"].as_str().unwrap_or("operation"),
                    event["phase"].as_str().unwrap_or("update"),
                    event
                        .get("error")
                        .map_or(String::new(), |error| format!(" — {error}")),
                    if event["operation"] == "validate" && event["phase"] == "ready" {
                        if event["data"]["passed"] == true {
                            " — Validation passed"
                        } else {
                            " — Validation failed"
                        }
                    } else {
                        ""
                    }
                ),
                view,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{rebind_target, run_limits_note};
    use serde_json::json;

    #[test]
    fn run_limits_are_listed_in_words() {
        assert_eq!(
            run_limits_note(&json!({"max_operations":null,"max_wakes_per_seat":50,"max_wall_clock_seconds":null,"stall_turns":0,"seat_turn_timeout_seconds":300,"max_output_tokens":null,"idle_turn_retries":2})).unwrap(),
            "Run limits: operations no limit; wakes per seat 50; wall clock no limit; turn timeout 300 s; output tokens per request provider default. Set them with the roster `limits` object when entering."
        );
        assert_eq!(run_limits_note(&json!(null)), None);
    }

    /// Entering opens the table; leaving returns to the builder the table
    /// was opened from, not the stale builder id the run saved, which is
    /// only the fallback.
    #[test]
    fn leave_returns_to_the_session_the_table_was_opened_from() {
        assert_eq!(
            rebind_target(&json!({"session": {"activeSessionId": "table"}}), None),
            Some("table".to_owned())
        );
        let left = json!({"builder_session_id": "before-restart"});
        assert_eq!(
            rebind_target(&left, Some("builder-now".to_owned())),
            Some("builder-now".to_owned())
        );
        assert_eq!(
            rebind_target(&left, None),
            Some("before-restart".to_owned())
        );
    }
}
