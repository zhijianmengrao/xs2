use std::time::Duration;

use serde::Serialize;
use tauri::{Manager, ResourceId, Runtime, Webview};
use tauri_plugin_updater::{Update, UpdaterExt};
use url::Url;

// fork 分发（R28 方案 A，2026-10 起收敛为单源）：更新源仅指向本仓库 GitHub Releases。
// 上游 R2 与 Gitee 源必须移除：tauri updater 在 check() 阶段不验签（仅下载时验签），
// 保留上游端点时其更高版本号（实测 1.1.1 / v1.0.10）会穿透成“发现新版本”误报，且下载必败。
const GITHUB_UPDATE_ENDPOINT: &str =
    "https://github.com/zhijianmengrao/xs2/releases/latest/download/latest.json";
const UPDATE_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateMetadata {
    rid: ResourceId,
    #[serde(skip_serializing_if = "Option::is_none")]
    fallback_rid: Option<ResourceId>,
    current_version: String,
    version: String,
    date: Option<String>,
    body: Option<String>,
    raw_json: serde_json::Value,
}

async fn check_endpoint<R: Runtime>(
    webview: Webview<R>,
    endpoint: Result<Url, String>,
) -> Result<Option<Update>, String> {
    let endpoint = endpoint?;
    if endpoint.scheme() != "https" {
        return Err("更新地址必须使用 HTTPS".to_string());
    }
    let updater = webview
        .updater_builder()
        .endpoints(vec![endpoint])
        .map_err(|error| error.to_string())?
        .timeout(UPDATE_TIMEOUT)
        .build()
        .map_err(|error| error.to_string())?;
    updater.check().await.map_err(|error| error.to_string())
}

#[tauri::command]
pub async fn check_update_sources<R: Runtime>(
    webview: Webview<R>,
) -> Result<Option<UpdateMetadata>, String> {
    let github_url = Url::parse(GITHUB_UPDATE_ENDPOINT).map_err(|error| error.to_string());
    let update = check_endpoint(webview.clone(), github_url).await?;
    Ok(update.map(|update| UpdateMetadata {
        current_version: update.current_version.clone(),
        version: update.version.clone(),
        date: update.date.map(|date| date.to_string()),
        body: update.body.clone(),
        raw_json: update.raw_json.clone(),
        rid: webview.resources_table().add(update),
        fallback_rid: None,
    }))
}
