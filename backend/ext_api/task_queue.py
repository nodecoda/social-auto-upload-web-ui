"""
任务队列系统 - asyncio Queue + Worker 模式
支持并发控制、失败重试（指数退避）、进度追踪
"""

import asyncio
import json
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from impl.registry import get_platform
from util._logger import get_channel_logger

# R7: 状态枚举 + 聚合逻辑的唯一真源（原本地定义迁移到 util/status.py，
# 此处 re-export 保持外部 from ext_api.task_queue import TaskStatus 兼容）
from util.status import TaskStatus

logger = get_channel_logger("task_queue")

DB_PATH = BASE_DIR / "db" / "database.db"


@dataclass
class PublishTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str = ''                       # 新增
    platform: str = ""
    platform_type: int = 0  # 1=小红书 2=视频号 3=抖音 4=快手 5=B站
    account_name: str = ""
    account_cookie_path: str = ""
    video_path: str = ""
    title: str = ""
    description: str = ""
    thumbnail_path: str = ""
    tags: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    publish_url: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat())
    started_at: str | None = None
    finished_at: str | None = None

    # 新增：个性化配置字段
    video_landscape: dict | None = None
    video_portrait: dict | None = None
    cover_landscape: dict | None = None
    cover_portrait: dict | None = None
    video_format: str | None = None
    enable_timer: int | None = None
    schedule_time: str | None = None
    ai_content: str | None = None
    is_original: bool | None = None

    # 草稿批量发布溯源字段（Task 10 扩展）
    source: str = ''                # '' | 'draft' | 'normal'
    draft_id: int = 0
    account_id: int = 0
    detail_id: str = ''            # publish_details.id
    payload: dict = field(default_factory=dict)
    publish_kind: str = 'video'  # 'video' | 'image'（R6 队列三合一：同一队列按 kind 分发）

    def to_dict(self):
        d = asdict(self)
        d['tags'] = json.dumps(self.tags, ensure_ascii=False)
        # payload 不持久化（仅 in-memory 透传），不写入 d
        return d

    @classmethod
    def from_row(cls, row_dict):
        """从数据库行构造"""
        tags = row_dict.get('tags', '[]')
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        return cls(
            id=row_dict['id'],
            batch_id=row_dict.get('batch_id', ''),
            platform=row_dict['platform'],
            platform_type=row_dict.get('platform_type', 0),
            account_name=row_dict['account_name'],
            account_cookie_path=row_dict.get('account_cookie_path', ''),
            video_path=row_dict['video_path'],
            title=row_dict['title'],
            description=row_dict.get('description', ''),
            thumbnail_path=row_dict.get('thumbnail_path', ''),
            tags=tags,
            status=row_dict['status'],
            retry_count=row_dict.get('retry_count', 0),
            max_retries=row_dict.get('max_retries', 3),
            error_message=row_dict.get('error_message', ''),
            publish_url=row_dict.get('publish_url', ''),
            created_at=row_dict['created_at'],
            started_at=row_dict.get('started_at'),
            finished_at=row_dict.get('finished_at'),
            source=row_dict.get('source', ''),
            draft_id=row_dict.get('draft_id', 0),
            account_id=row_dict.get('account_id', 0),
            detail_id=row_dict.get('detail_id', ''),
        )


def _build_account_configs(task: 'PublishTask') -> dict:
    """构造写入 publish_details.account_configs 的 dict。
    含全 per-platform form 字段，让历史卡片能完整还原发布时的内容。"""
    return {
        'title': task.title,
        'description': task.description,
        'tags': task.tags,
        'thumbnail_path': task.thumbnail_path,
        'platform_type': task.platform_type,
        'videoLandscape': task.video_landscape,
        'videoPortrait': task.video_portrait,
        'coverLandscape': task.cover_landscape,
        'coverPortrait': task.cover_portrait,
        'videoFormat': task.video_format,
        'enableTimer': task.enable_timer,
        'scheduleTime': task.schedule_time,
        'aiContent': task.ai_content,
        'isOriginal': task.is_original,
    }



def _friendly_error_message(exc: Exception) -> str:
    """把浏览器自动化异常翻译成面向用户的文案。

    用户手动关闭浏览器时 Playwright 会抛 "Browser has been closed" /
    "Target page, context or browser has been closed" 等；其余按
    旧 publish_executor 的文案格式兜底（'发布失败: ...'）。
    """
    err_msg = str(exc)
    if "has been closed" in err_msg or "Target page" in err_msg:
        return '用户关闭了浏览器，发布已取消'
    return f'发布失败: {err_msg}'

class TaskQueue:
    """基于 asyncio 的任务队列，在后台线程中运行"""

    def __init__(self, max_concurrent: int = 2):
        self.queue: asyncio.Queue | None = None
        self.running: dict[str, PublishTask] = {}
        self.completed: list[PublishTask] = []
        self.max_concurrent = max_concurrent
        self._workers: list[asyncio.Task] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._status_callbacks: list = []  # 状态变更回调

    def start(self):
        """在后台线程中启动事件循环"""
        if self._started:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._started = True
        logger.info(f"[TaskQueue] 启动，并发数={self.max_concurrent}")
        # 由 _run_loop 初始化;这里保持 None 语义,使用时断言

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.queue = asyncio.Queue()
        for i in range(self.max_concurrent):
            self._loop.create_task(self._worker(f"worker-{i}"))
        self._loop.run_forever()

    async def _worker(self, name: str):
        assert self.queue is not None, "queue 未初始化(需先 start)"
        while True:
            task = await self.queue.get()
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat()
            self.running[task.id] = task
            self._update_db(task)
            self._notify_status(task)

            try:
                await self._execute(task)
                task.status = TaskStatus.SUCCESS
            except asyncio.CancelledError:
                # 用户手动关闭了浏览器 → impl/_browser 的 watchdog/disconnected 会
                # cancel 当前发布子任务；翻译成友好文案（与旧 publish_executor 一致）
                task.status = TaskStatus.CANCELLED
                task.error_message = '用户关闭了浏览器，发布已取消'
            except Exception as e:  # noqa: BLE001 -- 捕获后恢复默认状态,防御性编码
                # 重试逻辑已禁用 — 长耗时任务(如视频上传)失败立即标记 FAILED,
                # 避免误触发「同一任务再次开浏览器重新上传」
                task.status = TaskStatus.FAILED
                task.error_message = _friendly_error_message(e)

            finally:
                task.finished_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat()
                if task.id in self.running:
                    del self.running[task.id]
                self.completed.append(task)
                self._update_db(task)
                self._notify_status(task)
                assert self.queue is not None
                self.queue.task_done()

    async def _execute(self, task: PublishTask):
        """调用上游 uploader 执行发布（R6 队列三合一：唯一执行内核）。

        - 所有任务必须携带 payload（postVideo / 草稿批量 / image 发布统一 splat）；
          payload 为空的旧 myUtils.postVideo 模块函数路径已随 R6 移除。
        - 按 publish_kind 分发：'video' → platform.publish_video，'image' →
          platform.publish_image（R5 后两者均已统一为 async，直接 await）。
        - 在独立子任务里跑：impl/_browser 的 watchdog 在用户关闭浏览器时会
          cancel 当前 asyncio task（= 这里的子任务），避免把 worker 主循环一起杀掉
          （否则队列再无人消费，后续任务全部卡死）。
        """
        if not task.payload:
            raise ValueError(
                f"任务缺少 payload（R6 起所有发布任务必须携带 payload），task={task.id}"
            )

        platform = get_platform(task.platform_type)
        if not platform:
            raise ValueError(f"不支持的平台类型: {task.platform_type}")

        publish_fn = (
            platform.publish_image if task.publish_kind == 'image' else platform.publish_video
        )

        inner = asyncio.create_task(publish_fn(**task.payload))
        result = await inner
        if not result:
            # 与旧 publish_executor job 语义一致：返回 falsy = 页面未跳转/校验未通过
            raise RuntimeError("发布失败：页面未跳转，表单校验未通过")
        return result

    def add_task(self, task: PublishTask):
        """线程安全地添加任务到队列"""
        if not self._started:
            self.start()
        task.status = TaskStatus.QUEUED
        self._insert_db(task)
        assert self.queue is not None and self._loop is not None, "队列未启动"
        asyncio.run_coroutine_threadsafe(self.queue.put(task), self._loop)
        logger.info(f"[TaskQueue] 任务已入队: {task.id} ({task.platform}/{task.account_name})")

    def cancel_task(self, task_id: str) -> bool:
        """取消任务（仅对 pending/queued 状态有效）"""
        for task in self.completed:
            if task.id == task_id and task.status == TaskStatus.FAILED:
                # 将失败任务移回队列重试
                task.retry_count = 0
                task.error_message = ""
                task.status = TaskStatus.QUEUED
                self.completed.remove(task)
                assert self.queue is not None and self._loop is not None
                asyncio.run_coroutine_threadsafe(self.queue.put(task), self._loop)
                self._update_db(task)
                return True
        return False

    def retry_task(self, task_id: str) -> bool:
        """重试失败的任务"""
        for task in list(self.completed):
            if task.id == task_id and task.status == TaskStatus.FAILED:
                task.retry_count = 0
                task.error_message = ""
                task.status = TaskStatus.QUEUED
                self.completed.remove(task)
                assert self.queue is not None and self._loop is not None
                asyncio.run_coroutine_threadsafe(self.queue.put(task), self._loop)
                self._update_db(task)
                return True
        return False

    def get_status(self) -> dict:
        """获取队列状态"""
        pending = self.queue.qsize() if self.queue else 0
        running_tasks = [
            {"id": t.id, "platform": t.platform, "account": t.account_name, "title": t.title}
            for t in self.running.values()
        ]
        return {
            "pending": pending,
            "running": len(self.running),
            "completed": len(self.completed),
            "running_tasks": running_tasks,
        }

    def on_status_change(self, callback):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)

    def _notify_status(self, task: PublishTask):
        for cb in self._status_callbacks:
            try:
                cb(task)
            except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
                logger.info(f"[TaskQueue] 回调错误: {e}")

    # ========== 数据库操作 ==========

    def _insert_db(self, task: PublishTask):
        """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details。

        A1: 收敛到 services.publish_history._record_publish（唯一 writer）。
        source/draft_id 溯源（草稿批量）与 account_configs（task 字段打包）在此组装。
        """
        try:
            from services.publish_history import _record_publish
            _record_publish(
                batch_id=task.batch_id or task.id,
                detail_id=task.id,
                platform=task.platform,
                account_id=task.account_id,
                account_name=task.account_name,
                video_path=task.video_path,
                title=task.title,
                description=task.description,
                tags=task.tags,
                status=task.status,
                started_at=task.created_at,
                account_configs=_build_account_configs(task),
                content_type=task.publish_kind,
                source=task.source or '',
                draft_id=task.draft_id or 0,
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[TaskQueue] 插入数据库失败: {e}")

    def _update_db(self, task: PublishTask):
        """更新 1 行 publish_details + 聚合 publish_batches 状态。

        A1: 收敛到 services.publish_history._update_publish_result（唯一 writer），
        聚合口径 A2：cancelled 归 fail，in-flight 保持 running。
        """
        try:
            from services.publish_history import _update_publish_result
            _update_publish_result(
                detail_id=task.id,
                status=task.status,
                finished_at=task.finished_at,
                error_message=task.error_message,
                retry_count=task.retry_count,
                publish_url=task.publish_url,
                started_at=task.started_at,
            )
        except Exception as e:  # noqa: BLE001 -- 统一兜底并记录调试日志,防御性编码
            logger.info(f"[TaskQueue] 更新数据库失败: {e}")



# 全局单例
# 强制单并发：任意时刻最多 1 个浏览器在发布（架构整改 #8 队列统一，
# 替代原 services/publish_executor 单工作线程语义，杜绝并发开多个浏览器）。
task_queue = TaskQueue(max_concurrent=1)


def get_task_queue() -> TaskQueue:
    return task_queue
