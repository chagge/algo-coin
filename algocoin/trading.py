from typing import Callable
from .backtest import Backtest
from .lib.callback import Callback, Print
from .lib.config import TradingEngineConfig
from .lib.enums import TradingType
from .execution import Execution
from .risk import Risk
from .lib.strategy import TradingStrategy
from .lib.structs import TradeRequest, TradeResponse
from .lib.utils import ex_type_to_ex
from .lib.logging import LOG as log
# import time


class TradingEngine(object):
    def __init__(self, options: TradingEngineConfig) -> None:
        self._live = options.type == TradingType.LIVE
        self._sandbox = options.type == TradingType.SANDBOX
        self._backtest = options.type == TradingType.BACKTEST
        self._print = options.print

        self._strats = []  # type: List[TradingStrategy]

        self._ex = ex_type_to_ex(options.exchange_options.exchange_type)(options.exchange_options)

        log.info(self._ex.accounts())

        self._bt = Backtest(options.backtest_options) if self._backtest else None

        self._rk = Risk(options.risk_options)

        self._ec = Execution(options.execution_options, self._ex)

        if self._print:
            log.warn('WARNING: Running in verbose mode')

            if self._live or self._sandbox:
                self._ex.registerCallback(
                    Print(onMatch=True,
                          onReceived=False,
                          onOpen=False,
                          onDone=False,
                          onChange=False,
                          onError=False))

            if self._backtest:
                self._bt.registerCallback(Print())

        self._ticked = []  # type: List
        self._trading = True  # type: bool

    def exchange(self):
        return self._ex

    def backtest(self):
        return self._bt

    def risk(self):
        return self._rk

    def execution(self):
        return self._ec

    def haltTrading(self):
        self._trading = False

    def continueTrading(self):
        self._trading = True

    def registerStrategy(self, strat: TradingStrategy):
        if self._live or self._sandbox:
            # register for exchange data
            self._ex.registerCallback(strat.callback())

        if self._backtest:
            # register for backtest data
            self._bt.registerCallback(strat.callback())

        # add to tickables
        self._strats.append(strat)  # add to tickables

        # give self to strat so it can request trading actions
        strat.setEngine(self)

    def run(self):
        if self._live or self._sandbox:
            self._ex.run(self)

        elif self._backtest:
            self._bt.run(self)

        else:
            raise Exception('Invalid configuration')

    def tick(self):
        for strat in self._strats:
            if strat.ticked():
                self._ticked.append(strat)
                strat.reset()

        self.ticked()

    def ticked(self):
        while len(self._ticked):
            self._ticked.pop()
            # strat = self._ticked.pop()
            # print('Strat ticked', strat, time.time())

    def requestBuy(self,
                   callback: Callable,
                   req: TradeRequest,
                   callback_failure=None):

        if not self._trading:
            resp = TradeResponse(success=False)

        else:
            resp = self._rk.requestBuy(req)

            if resp.risk_check:
                resp = self._ec.requestBuy(resp)
                self._rk.update(resp)

        callback_failure(resp) if callback_failure and not resp.success else callback(resp)

    def requestSell(self,
                    callback: Callable,
                    req: TradeRequest,
                    callback_failure=None):

        if not self._trading:
            resp = TradeResponse(success=False)

        else:
            resp = self._rk.requestSell(req)

            if resp.risk_check:
                resp = self._ec.requestSell(resp)
                self._rk.update(resp)

        callback_failure(resp) if callback_failure and not resp.success else callback(resp)
