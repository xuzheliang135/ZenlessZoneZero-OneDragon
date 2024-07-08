from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Optional, Callable

from one_dragon.base.operation.application_run_record import AppRunRecord
from one_dragon.base.operation.context_base import ContextBase
from one_dragon.base.operation.operation import Operation
from one_dragon.base.operation.operation_base import OperationResult

_app_preheat_executor = ThreadPoolExecutor(thread_name_prefix='od_app_preheat', max_workers=1)


class ApplicationEventId(Enum):

    APPLICATION_START: str = '应用开始运行'


class Application(Operation):

    def __init__(self, ctx: ContextBase,
                 node_max_retry_times: int = 1,
                 op_name: str = None,
                 timeout_seconds: float = -1,
                 op_callback: Optional[Callable[[OperationResult], None]] = None,
                 check_game_win: bool = True,
                 op_to_enter_game: Optional[Operation] = None,
                 init_context_before_start: bool = True,
                 stop_context_after_stop: bool = True,
                 run_record: Optional[AppRunRecord] = None):
        super().__init__(ctx, node_max_retry_times=node_max_retry_times, op_name=op_name,
                         timeout_seconds=timeout_seconds,
                         op_callback=op_callback,
                         check_game_win=check_game_win,
                         op_to_enter_game=op_to_enter_game)

        self.run_record: Optional[AppRunRecord] = run_record
        """运行记录"""

        self.init_context_before_start: bool = init_context_before_start
        """运行前是否初始化上下文 一条龙只有第一个应用需要"""

        self.stop_context_after_stop: bool = stop_context_after_stop
        """运行后是否停止上下文 一条龙只有最后一个应用需要"""

    def _init_before_execute(self) -> None:
        Operation._init_before_execute(self)
        if self.run_record is not None:
            self.run_record.update_status(AppRunRecord.STATUS_RUNNING)

        self.ctx.start_running()
        self.ctx.dispatch_event(ApplicationEventId.APPLICATION_START.value)

    def handle_resume(self) -> None:
        """
        恢复运行后的处理 由子类实现
        :return:
        """
        self.ctx.controller.init()

    def _after_operation_done(self, result: OperationResult):
        """
        停止后的处理
        :return:
        """
        super()._after_operation_done(result)
        self._update_record_after_stop(result)
        if self.stop_context_after_stop:
            self.ctx.stop_running()

    def _update_record_after_stop(self, result: OperationResult):
        """
        应用停止后的对运行记录的更新
        :param result: 运行结果
        :return:
        """
        if self.run_record is not None:
            if result.success:
                self.run_record.update_status(AppRunRecord.STATUS_SUCCESS)
            else:
                self.run_record.update_status(AppRunRecord.STATUS_FAIL)

    @property
    def current_execution_desc(self) -> str:
        """
        当前运行的描述 用于UI展示
        :return:
        """
        return ''

    @property
    def next_execution_desc(self) -> str:
        """
        下一步运行的描述 用于UI展示
        :return:
        """
        return ''

    @staticmethod
    def get_preheat_executor() -> ThreadPoolExecutor:
        return _app_preheat_executor