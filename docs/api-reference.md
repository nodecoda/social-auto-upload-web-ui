# API 参考（自动生成）

> 由 `backend/scripts/gen_api_docs.py` 从 Flask 路由表生成，路由变更后重跑刷新。
> 共 116 条路由（不含 static）。

## 路由总表

| 方法 | 路径 | endpoint | 说明 | 前端 api 层 |
| --- | --- | --- | --- | --- |
| GET | `/` | `index` | 前端 SPA 入口：返回 frontend/dist/index.html（不存在则报 API 存活）。 |  |
| GET | `/api/accounts/<int:account_id>/tags` | `account.get_account_tags` | 获取单个账号的标签列表。 | account.ts / user.ts |
| PUT | `/api/accounts/<int:account_id>/tags` | `account.set_account_tags` | 设置单个账号的标签（整体覆盖）。 | account.ts / user.ts |
| PUT | `/api/accounts/batch/tags` | `account.set_batch_account_tags` | 批量为多个账号添加相同的标签(追加模式:不清除已有标签) | account.ts / user.ts |
| GET | `/api/alipay/compilation-search` | `alipay.search_compilation` | 搜索支付宝合集 —— 浏览器拦截 queryCompilationsByPublicId.json。 | alipay.ts |
| GET | `/api/alipay/music-list` | `alipay.music_list` | 获取支付宝图集背景音乐列表(全量返回,前端客户端分页)。 | alipay.ts |
| GET | `/api/bilibili/collections` | `bilibili.list_collections` | 获取账号的合集列表。 | bilibili.ts |
| GET | `/api/channels/activities` | `channels.list_activities` | 搜索可参与的活动列表。 | channels.ts |
| GET | `/api/channels/collections` | `channels.list_collections` | 获取账号的合集列表。 | channels.ts |
| GET | `/api/channels/locations` | `channels.list_locations` | 搜索账号附近的位置列表。 | channels.ts |
| POST | `/api/clear-cache` | `frames.clear_cache` | Clear cached data: extracted frames, old logs, etc. | frame.ts |
| GET | `/api/douyin-image/activity-list` | `douyin_image.get_activity_list` | 获取官方活动列表 | douyinImage.ts |
| GET | `/api/douyin-image/hotspot-search` | `douyin_image.search_hotspot` | 搜索热点 | douyinImage.ts |
| GET | `/api/douyin-image/mix-list` | `douyin_image.get_mix_list` | 获取用户的合集列表 | douyinImage.ts |
| GET | `/api/douyin-image/music-search` | `douyin_image.search_music` | 搜索音乐 - 通过浏览器拦截网络请求获取结果 | douyinImage.ts |
| GET | `/api/douyin-image/search-game` | `douyin_image.search_game` | 搜索游戏 | douyinImage.ts |
| GET | `/api/douyin-image/search-mark-spu` | `douyin_image.search_mark_spu` | 搜索标记万物商品 | douyinImage.ts |
| GET | `/api/douyin-image/search-medium` | `douyin_image.search_medium` | 搜索影视演绎 | douyinImage.ts |
| GET | `/api/douyin-image/search-miniapp` | `douyin_image.search_miniapp` | 搜索小程序 - 通过链接查询 | douyinImage.ts |
| GET | `/api/douyin-image/search-poi` | `douyin_image.search_poi` | 搜索位置 | douyinImage.ts |
| POST | `/api/extract-frames` | `frames.extract_frames` | 提取视频抽帧：material_id 或 video_path 指定素材，后台生成帧列表。 | frame.ts |
| GET | `/api/feedback/list` | `feedback.feedback_list` | 状态筛选：全部 / 待确认 / 处理中 / 已完成 / 已拒绝 | feedback.ts |
| POST | `/api/feedback/submit` | `feedback.feedback_submit` | 提交反馈：表单+附件透传上游，邮箱缺省读 settings.feedbackEmail。 | feedback.ts |
| POST | `/api/feedback/vote` | `feedback.feedback_vote` | 反馈点赞/有用投票：body 传 id+email，邮箱缺省读 settings。 | feedback.ts |
| GET | `/api/frame-image` | `frames.get_frame_image` | 按秒数获取单帧图片（回源视频转码）。 | frame.ts |
| GET | `/api/frames` | `frames.get_frames` | 获取已抽取的帧列表（时间戳+URL）。 | frame.ts |
| GET | `/api/frames-status` | `frames.frames_status` | 查询抽帧任务状态/进度。 | frame.ts |
| GET | `/api/health` | `health_check` | 健康检查/诊断：数据目录、DB 存在性、Python 环境、user_info 计数。 |  |
| GET | `/api/image-proxy` | `image_proxy.image_proxy` | 头像代理：绕过 sinaimg.cn 防盗链。后端请求带 Referer=weibo.com。 |  |
| GET | `/api/image-publish/drafts` | `image_publish.get_drafts` | 获取图集草稿列表（重定向到统一接口） | imagePublish.ts |
| POST | `/api/image-publish/drafts` | `image_publish.save_draft` | 保存图集草稿（重定向到统一接口） | imagePublish.ts |
| DELETE | `/api/image-publish/drafts/<draft_id>` | `image_publish.delete_draft` | 删除图集草稿 | imagePublish.ts |
| POST | `/api/image-publish/drafts/batch-publish` | `image_publish.batch_publish_image_drafts` | 图集草稿批量发布：每个 draft 调一次 publish_images 走单账号链路。 | imagePublish.ts |
| POST | `/api/image-publish/execute-publish` | `image_publish.execute_publish` | 执行图集发布任务 - 调用平台API（单账号 + batchId 模式） | imagePublish.ts |
| POST | `/api/image-publish/publish` | `image_publish.publish_images` | 发布图集内容到各平台（单账号 + batchId 模式，前端循环调用） | imagePublish.ts |
| POST | `/api/jd/novel/search` | `jd_picker.novel_search` | 搜小说关键词,返回候选列表。 | jd.ts |
| POST | `/api/jd/picker/close` | `jd_picker.picker_close` | 关闭选择器会话并释放浏览器。 | jd.ts |
| POST | `/api/jd/picker/go_page` | `jd_picker.picker_go_page` | 翻页浏览搜索结果。 | jd.ts |
| POST | `/api/jd/picker/open` | `jd_picker.picker_open` | 打开京东关联商品选择器（后台浏览器+事件循环）。 | jd.ts |
| POST | `/api/jd/picker/search` | `jd_picker.picker_search` | 按关键词搜索京东商品。 | jd.ts |
| GET | `/api/kuaishou-image/music-search` | `kuaishou_image.search_music` | 搜索音乐 - 通过浏览器拦截网络请求获取结果 | kuaishouImage.ts |
| GET | `/api/kuaishou-image/ping` | `kuaishou_image.ping` | 快手图集 blueprint 存活探针。 | kuaishouImage.ts |
| DELETE | `/api/materials/<material_id>` | `materials.delete` | 删除素材 | materials.ts / upload.ts |
| GET | `/api/materials/<material_id>` | `materials.get_material` | 按 id 获取素材详情（含存储类型解析）。 | materials.ts / upload.ts |
| POST | `/api/materials/<material_id>/probe` | `materials.probe` | 识别存量视频的 duration 与 file_size 并写库，返回最新记录。 | materials.ts / upload.ts |
| POST | `/api/materials/batch-delete` | `materials.batch_delete` | 批量删除素材。 | materials.ts / upload.ts |
| POST | `/api/materials/covers/upload` | `materials.covers_upload` | 封面专用上传：写 covers/ 目录，不入素材库（materials 表）。 | materials.ts / upload.ts |
| GET | `/api/materials/file/<path:relative_path>` | `materials.serve_file` | 文件访问 — 按素材自身的存储方式提供文件 | materials.ts / upload.ts |
| GET | `/api/materials/list` | `materials.list_files` | 分页素材列表 | materials.ts / upload.ts |
| POST | `/api/materials/test-s3` | `materials.test_s3_connection` | 测试 S3 连接 | materials.ts / upload.ts |
| POST | `/api/materials/upload` | `materials.upload` | 统一文件上传（流式：避免大文件 OOM） | materials.ts / upload.ts |
| GET | `/api/system-info` | `frames.system_info` | Return version and cache size info. | frame.ts |
| GET | `/api/tags` | `account.get_tags` | 获取全部标签列表。 | account.ts / user.ts |
| POST | `/api/tags` | `account.create_tag` | 新建标签（名称去重）。 | account.ts / user.ts |
| DELETE | `/api/tags/<int:tag_id>` | `account.delete_tag` | 按 id 删除标签。 | account.ts / user.ts |
| POST | `/api/taobao_guanghe/picker/close` | `taobao_guanghe.picker_close` | 关闭选择器会话并释放浏览器。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/filter` | `taobao_guanghe.picker_filter` | 应用筛选条件到当前列表。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/load_more` | `taobao_guanghe.picker_load_more` | 加载下一页/滚动加载更多。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/open` | `taobao_guanghe.picker_open` | 打开弹窗 → 启动浏览器并进入选择面板。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/search` | `taobao_guanghe.picker_search` | 按关键词搜索光合面板内容。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/switch_type` | `taobao_guanghe.picker_switch_type` | 切换商品↔店铺。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/tab` | `taobao_guanghe.picker_tab` | 切换选择面板标签页（商品/店铺/图片）。 | taobaoGuanghe.ts |
| GET | `/api/toutiao/compilation-search` | `toutiao.search_compilation` | 搜索头条合集 —— 浏览器拦截 pSeries/simpleGetAlbumInfoByMediaId。 | toutiao.ts |
| DELETE | `/api/uploads/` | `uploads.cancel_upload` | 取消上传 + 清理临时文件 + DB 记录标记 cancelled。 |  |
| POST | `/api/uploads/chunk` | `uploads.upload_chunk` | 接收单个分片。 |  |
| POST | `/api/uploads/init` | `uploads.init_upload` | 初始化上传会话。 |  |
| POST | `/api/uploads/merge` | `uploads.merge_chunks` | 合并所有分片 → 写入 materials 表 → 清理临时文件。 |  |
| GET | `/api/uploads/status` | `uploads.status` | 查询已上传分片（断点续传用）。 |  |
| GET | `/api/v2/changelog` | `ext_api.get_changelog` | 获取更新日志列表（按文件名倒序） | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/drafts` | `ext_api.get_drafts` | 获取草稿列表（支持 type 过滤：video/image） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/drafts` | `ext_api.create_draft` | 创建草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/drafts/<int:draft_id>` | `ext_api.delete_draft` | 删除草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/drafts/<int:draft_id>` | `ext_api.get_draft` | 获取草稿详情 | draft.ts / v2.ts / frame.ts / changelog.ts |
| PUT | `/api/v2/drafts/<int:draft_id>` | `ext_api.update_draft` | 更新草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/drafts/batch` | `ext_api.batch_delete_drafts` | 视频草稿批量删除。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/drafts/batch-publish` | `ext_api.batch_publish_drafts` | 视频草稿批量发布：每个 (draft, account) 入队 1 个 task。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/history` | `ext_api.get_history` | 获取发布历史（按批次分组），支持分页、平台/状态/类型过滤 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/history/<batch_id>` | `ext_api.delete_history_batch` | 删除单条发布历史记录。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/history/<batch_id>` | `ext_api.get_history_batch` | 获取单个发布批次详情（含所有明细） | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/history/batch` | `ext_api.batch_delete_history` | 发布历史批量删除。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/publish-templates` | `ext_api.get_publish_templates` | 一键填写：从历史成功/部分成功批次里取可复用的 per-channel 配置。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/queue/status` | `ext_api.queue_status` | 获取任务队列状态 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/settings` | `ext_api.get_settings` | 获取系统设置 | draft.ts / v2.ts / frame.ts / changelog.ts |
| PUT | `/api/v2/settings` | `ext_api.update_settings` | 更新系统设置 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/stats` | `ext_api.get_stats` | 获取统计数据（成功率、发布量趋势等） | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks` | `ext_api.get_tasks` | 获取任务列表（读 publish_details，每行 = 1 个账号 × 1 个平台） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks` | `ext_api.create_task` | 创建发布任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks/<detail_id>` | `ext_api.get_task` | 获取单个任务（按 publish_details.id 查） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks/<task_id>/cancel` | `ext_api.cancel_task` | 取消任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks/<task_id>/retry` | `ext_api.retry_task` | 重试失败任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks/stream` | `ext_api.task_stream` | SSE 实时推送任务状态变更 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/vivo/search-position` | `vivo.search_position` | 搜索 VIVO 添加位置。 | vivo.ts |
| GET | `/api/weibo/collections` | `weibo.list_collections` | 获取微博账号的视频合集列表。 | weibo.ts |
| GET | `/api/weixin_gzh/collections` | `weixin_gzh.list_collections` | 获取账号的合集列表(视频合集 / 贴图合集)。 | weixin_gzh.ts |
| GET | `/api/xiaohongshu/collections` | `xiaohongshu.list_collections` | 获取账号的合集列表。 | xiaohongshu.ts |
| GET | `/api/xiaohongshu/search-poi` | `xiaohongshu.search_poi` | 搜索拍摄地点 POI。 | xiaohongshu.ts |
| GET | `/assets/<path:filename>` | `custom_static` | 前端构建产物静态资源（frontend/dist/assets）。 |  |
| GET | `/changelog/<path:filename>` | `serve_changelog` | 更新日志静态文件（changelog/ 目录，打包目录缺失时回退 BASE_DIR）。 |  |
| GET | `/checkAccount` | `account.check_account` | 校验单个账号 cookie 是否有效（浏览器验证）。 | account.ts / user.ts |
| DELETE | `/deleteAccount` | `account.delete_account` | 按 id 删除账号。 | account.ts / user.ts |
| GET | `/downloadCookie` | `account.download_cookie` | 按 filePath 下载账号 cookie 文件。 | account.ts / user.ts |
| GET | `/favicon.ico` | `favicon` | 站点 favicon（frontend/dist/favicon.ico）。 |  |
| GET | `/getAccounts` | `account.getAccounts` | 获取全部账号列表（含标签聚合）。 | account.ts / user.ts |
| GET | `/getValidAccounts` | `account.getValidAccounts` | 获取所有账号并使用新引擎逐个验证 cookie 有效性 | account.ts / user.ts |
| POST | `/importAccount` | `account.import_account_start` | 启动一个 cookie 导入任务。 | account.ts / user.ts |
| GET | `/importAccount/stream` | `account.import_account_stream` | SSE 推送 cookie 导入进度。 | account.ts / user.ts |
| GET | `/login` | `account.login` | 平台登录：发起扫码/账号登录，返回 SSE 流式状态。 | account.ts / user.ts |
| POST | `/openCreatorCenter` | `account.open_creator_center` | 打开平台创作者中心页面（登录态确认）。 | account.ts / user.ts |
| GET | `/platforms/import-supported` | `account.platforms_import_supported` | 列出所有支持 cookie 字符串导入的平台。 | account.ts / user.ts |
| POST | `/postVideo` | `publish.postVideo` | 发布视频：校验+入队后台串行执行器，立即返回 taskId（前端轮询 status）。 | draft.ts / v2.ts |
| GET | `/postVideo/status/<task_id>` | `publish.postVideo_status` | 查询异步发布任务状态（前端在发布期间轮询本接口）。 | draft.ts / v2.ts |
| POST | `/postVideoBatch` | `publish.postVideoBatch` | 批量发布视频（同步调用）：逐条校验/发布，失败项聚合到 errors 返回。 | draft.ts / v2.ts |
| POST | `/syncProfile` | `account.sync_profile` | 同步账号主页资料（昵称/头像/粉丝数等）。 | account.ts / user.ts |
| POST | `/updateUserinfo` | `account.updateUserinfo` | 更新账号信息（昵称/备注等）。 | account.ts / user.ts |
| POST | `/uploadCookie` | `account.upload_cookie` | 上传账号 cookie 文件并更新账号状态。 | account.ts / user.ts |
| GET | `/vite.svg` | `vite_svg` | Vite 默认 logo（frontend/dist/vite.svg）。 |  |

## 按域分组

### account

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/accounts/<int:account_id>/tags` | 获取单个账号的标签列表。 | account.ts / user.ts |
| PUT | `/api/accounts/<int:account_id>/tags` | 设置单个账号的标签（整体覆盖）。 | account.ts / user.ts |
| PUT | `/api/accounts/batch/tags` | 批量为多个账号添加相同的标签(追加模式:不清除已有标签) | account.ts / user.ts |
| GET | `/api/tags` | 获取全部标签列表。 | account.ts / user.ts |
| POST | `/api/tags` | 新建标签（名称去重）。 | account.ts / user.ts |
| DELETE | `/api/tags/<int:tag_id>` | 按 id 删除标签。 | account.ts / user.ts |
| GET | `/checkAccount` | 校验单个账号 cookie 是否有效（浏览器验证）。 | account.ts / user.ts |
| DELETE | `/deleteAccount` | 按 id 删除账号。 | account.ts / user.ts |
| GET | `/downloadCookie` | 按 filePath 下载账号 cookie 文件。 | account.ts / user.ts |
| GET | `/getAccounts` | 获取全部账号列表（含标签聚合）。 | account.ts / user.ts |
| GET | `/getValidAccounts` | 获取所有账号并使用新引擎逐个验证 cookie 有效性 | account.ts / user.ts |
| POST | `/importAccount` | 启动一个 cookie 导入任务。 | account.ts / user.ts |
| GET | `/importAccount/stream` | SSE 推送 cookie 导入进度。 | account.ts / user.ts |
| GET | `/login` | 平台登录：发起扫码/账号登录，返回 SSE 流式状态。 | account.ts / user.ts |
| POST | `/openCreatorCenter` | 打开平台创作者中心页面（登录态确认）。 | account.ts / user.ts |
| GET | `/platforms/import-supported` | 列出所有支持 cookie 字符串导入的平台。 | account.ts / user.ts |
| POST | `/syncProfile` | 同步账号主页资料（昵称/头像/粉丝数等）。 | account.ts / user.ts |
| POST | `/updateUserinfo` | 更新账号信息（昵称/备注等）。 | account.ts / user.ts |
| POST | `/uploadCookie` | 上传账号 cookie 文件并更新账号状态。 | account.ts / user.ts |

### alipay

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/alipay/compilation-search` | 搜索支付宝合集 —— 浏览器拦截 queryCompilationsByPublicId.json。 | alipay.ts |
| GET | `/api/alipay/music-list` | 获取支付宝图集背景音乐列表(全量返回,前端客户端分页)。 | alipay.ts |

### app(装配层)

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/` | 前端 SPA 入口：返回 frontend/dist/index.html（不存在则报 API 存活）。 |  |
| GET | `/api/health` | 健康检查/诊断：数据目录、DB 存在性、Python 环境、user_info 计数。 |  |
| GET | `/assets/<path:filename>` | 前端构建产物静态资源（frontend/dist/assets）。 |  |
| GET | `/changelog/<path:filename>` | 更新日志静态文件（changelog/ 目录，打包目录缺失时回退 BASE_DIR）。 |  |
| GET | `/favicon.ico` | 站点 favicon（frontend/dist/favicon.ico）。 |  |
| GET | `/vite.svg` | Vite 默认 logo（frontend/dist/vite.svg）。 |  |

### bilibili

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/bilibili/collections` | 获取账号的合集列表。 | bilibili.ts |

### channels

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/channels/activities` | 搜索可参与的活动列表。 | channels.ts |
| GET | `/api/channels/collections` | 获取账号的合集列表。 | channels.ts |
| GET | `/api/channels/locations` | 搜索账号附近的位置列表。 | channels.ts |

### douyin_image

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/douyin-image/activity-list` | 获取官方活动列表 | douyinImage.ts |
| GET | `/api/douyin-image/hotspot-search` | 搜索热点 | douyinImage.ts |
| GET | `/api/douyin-image/mix-list` | 获取用户的合集列表 | douyinImage.ts |
| GET | `/api/douyin-image/music-search` | 搜索音乐 - 通过浏览器拦截网络请求获取结果 | douyinImage.ts |
| GET | `/api/douyin-image/search-game` | 搜索游戏 | douyinImage.ts |
| GET | `/api/douyin-image/search-mark-spu` | 搜索标记万物商品 | douyinImage.ts |
| GET | `/api/douyin-image/search-medium` | 搜索影视演绎 | douyinImage.ts |
| GET | `/api/douyin-image/search-miniapp` | 搜索小程序 - 通过链接查询 | douyinImage.ts |
| GET | `/api/douyin-image/search-poi` | 搜索位置 | douyinImage.ts |

### ext_api

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/v2/changelog` | 获取更新日志列表（按文件名倒序） | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/drafts` | 获取草稿列表（支持 type 过滤：video/image） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/drafts` | 创建草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/drafts/<int:draft_id>` | 删除草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/drafts/<int:draft_id>` | 获取草稿详情 | draft.ts / v2.ts / frame.ts / changelog.ts |
| PUT | `/api/v2/drafts/<int:draft_id>` | 更新草稿 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/drafts/batch` | 视频草稿批量删除。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/drafts/batch-publish` | 视频草稿批量发布：每个 (draft, account) 入队 1 个 task。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/history` | 获取发布历史（按批次分组），支持分页、平台/状态/类型过滤 | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/history/<batch_id>` | 删除单条发布历史记录。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/history/<batch_id>` | 获取单个发布批次详情（含所有明细） | draft.ts / v2.ts / frame.ts / changelog.ts |
| DELETE | `/api/v2/history/batch` | 发布历史批量删除。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/publish-templates` | 一键填写：从历史成功/部分成功批次里取可复用的 per-channel 配置。 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/queue/status` | 获取任务队列状态 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/settings` | 获取系统设置 | draft.ts / v2.ts / frame.ts / changelog.ts |
| PUT | `/api/v2/settings` | 更新系统设置 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/stats` | 获取统计数据（成功率、发布量趋势等） | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks` | 获取任务列表（读 publish_details，每行 = 1 个账号 × 1 个平台） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks` | 创建发布任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks/<detail_id>` | 获取单个任务（按 publish_details.id 查） | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks/<task_id>/cancel` | 取消任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| POST | `/api/v2/tasks/<task_id>/retry` | 重试失败任务 | draft.ts / v2.ts / frame.ts / changelog.ts |
| GET | `/api/v2/tasks/stream` | SSE 实时推送任务状态变更 | draft.ts / v2.ts / frame.ts / changelog.ts |

### feedback

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/feedback/list` | 状态筛选：全部 / 待确认 / 处理中 / 已完成 / 已拒绝 | feedback.ts |
| POST | `/api/feedback/submit` | 提交反馈：表单+附件透传上游，邮箱缺省读 settings.feedbackEmail。 | feedback.ts |
| POST | `/api/feedback/vote` | 反馈点赞/有用投票：body 传 id+email，邮箱缺省读 settings。 | feedback.ts |

### frames

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| POST | `/api/clear-cache` | Clear cached data: extracted frames, old logs, etc. | frame.ts |
| POST | `/api/extract-frames` | 提取视频抽帧：material_id 或 video_path 指定素材，后台生成帧列表。 | frame.ts |
| GET | `/api/frame-image` | 按秒数获取单帧图片（回源视频转码）。 | frame.ts |
| GET | `/api/frames` | 获取已抽取的帧列表（时间戳+URL）。 | frame.ts |
| GET | `/api/frames-status` | 查询抽帧任务状态/进度。 | frame.ts |
| GET | `/api/system-info` | Return version and cache size info. | frame.ts |

### image_proxy

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/image-proxy` | 头像代理：绕过 sinaimg.cn 防盗链。后端请求带 Referer=weibo.com。 |  |

### image_publish

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/image-publish/drafts` | 获取图集草稿列表（重定向到统一接口） | imagePublish.ts |
| POST | `/api/image-publish/drafts` | 保存图集草稿（重定向到统一接口） | imagePublish.ts |
| DELETE | `/api/image-publish/drafts/<draft_id>` | 删除图集草稿 | imagePublish.ts |
| POST | `/api/image-publish/drafts/batch-publish` | 图集草稿批量发布：每个 draft 调一次 publish_images 走单账号链路。 | imagePublish.ts |
| POST | `/api/image-publish/execute-publish` | 执行图集发布任务 - 调用平台API（单账号 + batchId 模式） | imagePublish.ts |
| POST | `/api/image-publish/publish` | 发布图集内容到各平台（单账号 + batchId 模式，前端循环调用） | imagePublish.ts |

### jd_picker

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| POST | `/api/jd/novel/search` | 搜小说关键词,返回候选列表。 | jd.ts |
| POST | `/api/jd/picker/close` | 关闭选择器会话并释放浏览器。 | jd.ts |
| POST | `/api/jd/picker/go_page` | 翻页浏览搜索结果。 | jd.ts |
| POST | `/api/jd/picker/open` | 打开京东关联商品选择器（后台浏览器+事件循环）。 | jd.ts |
| POST | `/api/jd/picker/search` | 按关键词搜索京东商品。 | jd.ts |

### kuaishou_image

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/kuaishou-image/music-search` | 搜索音乐 - 通过浏览器拦截网络请求获取结果 | kuaishouImage.ts |
| GET | `/api/kuaishou-image/ping` | 快手图集 blueprint 存活探针。 | kuaishouImage.ts |

### materials

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| DELETE | `/api/materials/<material_id>` | 删除素材 | materials.ts / upload.ts |
| GET | `/api/materials/<material_id>` | 按 id 获取素材详情（含存储类型解析）。 | materials.ts / upload.ts |
| POST | `/api/materials/<material_id>/probe` | 识别存量视频的 duration 与 file_size 并写库，返回最新记录。 | materials.ts / upload.ts |
| POST | `/api/materials/batch-delete` | 批量删除素材。 | materials.ts / upload.ts |
| POST | `/api/materials/covers/upload` | 封面专用上传：写 covers/ 目录，不入素材库（materials 表）。 | materials.ts / upload.ts |
| GET | `/api/materials/file/<path:relative_path>` | 文件访问 — 按素材自身的存储方式提供文件 | materials.ts / upload.ts |
| GET | `/api/materials/list` | 分页素材列表 | materials.ts / upload.ts |
| POST | `/api/materials/test-s3` | 测试 S3 连接 | materials.ts / upload.ts |
| POST | `/api/materials/upload` | 统一文件上传（流式：避免大文件 OOM） | materials.ts / upload.ts |

### publish

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| POST | `/postVideo` | 发布视频：校验+入队后台串行执行器，立即返回 taskId（前端轮询 status）。 | draft.ts / v2.ts |
| GET | `/postVideo/status/<task_id>` | 查询异步发布任务状态（前端在发布期间轮询本接口）。 | draft.ts / v2.ts |
| POST | `/postVideoBatch` | 批量发布视频（同步调用）：逐条校验/发布，失败项聚合到 errors 返回。 | draft.ts / v2.ts |

### taobao_guanghe

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| POST | `/api/taobao_guanghe/picker/close` | 关闭选择器会话并释放浏览器。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/filter` | 应用筛选条件到当前列表。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/load_more` | 加载下一页/滚动加载更多。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/open` | 打开弹窗 → 启动浏览器并进入选择面板。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/search` | 按关键词搜索光合面板内容。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/switch_type` | 切换商品↔店铺。 | taobaoGuanghe.ts |
| POST | `/api/taobao_guanghe/picker/tab` | 切换选择面板标签页（商品/店铺/图片）。 | taobaoGuanghe.ts |

### toutiao

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/toutiao/compilation-search` | 搜索头条合集 —— 浏览器拦截 pSeries/simpleGetAlbumInfoByMediaId。 | toutiao.ts |

### uploads

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| DELETE | `/api/uploads/` | 取消上传 + 清理临时文件 + DB 记录标记 cancelled。 |  |
| POST | `/api/uploads/chunk` | 接收单个分片。 |  |
| POST | `/api/uploads/init` | 初始化上传会话。 |  |
| POST | `/api/uploads/merge` | 合并所有分片 → 写入 materials 表 → 清理临时文件。 |  |
| GET | `/api/uploads/status` | 查询已上传分片（断点续传用）。 |  |

### vivo

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/vivo/search-position` | 搜索 VIVO 添加位置。 | vivo.ts |

### weibo

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/weibo/collections` | 获取微博账号的视频合集列表。 | weibo.ts |

### weixin_gzh

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/weixin_gzh/collections` | 获取账号的合集列表(视频合集 / 贴图合集)。 | weixin_gzh.ts |

### xiaohongshu

| 方法 | 路径 | 说明 | 前端 api 层 |
| --- | --- | --- | --- |
| GET | `/api/xiaohongshu/collections` | 获取账号的合集列表。 | xiaohongshu.ts |
| GET | `/api/xiaohongshu/search-poi` | 搜索拍摄地点 POI。 | xiaohongshu.ts |

## 待补 docstring 清单

共 0 条路由无 docstring（文档可读性缺口）：


