# 导入函数库
from jqdata import *
from jqlib.technical_analysis import *
from jqdata import finance 
import pandas as pd
import warnings
import numpy as np
import datetime
import time
import tushare as ts
from six import BytesIO

# 初始化函数，设定基准等等
def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 为全部交易品种设定固定值滑点
    set_slippage(FixedSlippage(0.01))
    #开启盘口撮合
    set_option('match_with_order_book', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    # log.set_level('order', 'error')
    ts.set_token('d36d566f61ff364b5b6824484426752e1bbbe092dfaaec2d9c2cd996')

    ### 股票相关设定 ###
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, \
    close_commission=0.0003, min_commission=5), type='stock')

      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG')
      # 收盘后运行
    run_daily(after_market_close, time='after_close', reference_security='000300.XSHG')

## 开盘前运行函数
def before_market_open(context):
    print('--------------------------------新的一天：%s' % str(context.current_dt))
    g.preClose = {}
    g.dragonLeader = []
    g.security = []
    g.positions = []
    body=read_file("trade/TestStockPool.csv")
    stockPool=pd.read_csv(BytesIO(body), index_col=0, header=0)
    body=read_file("output/NineSunScripture.csv")
    g.continuousBoard = pd.read_csv(BytesIO(body), index_col=0, header=0)
    
    today = context.current_dt.strftime("%Y-%m-%d")
    if today in stockPool.index.tolist():
        pool = stockPool.loc[today]['code']
        if len(pool) > 0:
            g.security = eval(pool)
            #从CSV文件中读取当天要打板的票
            for stock in g.security:
                price = attribute_history(stock, 1, unit='1d',\
                fields=['close'],skip_paused=True, df=True, fq='pre')
                g.preClose[stock] = price.iloc[0]['close']
    
    for stock in context.portfolio.positions:
        g.positions.append(stock)
        if stock not in g.security:
            g.security.append(stock)
            price = attribute_history(stock, 1, unit='1d',\
            fields=['close'],skip_paused=True, df=True, fq='pre')
            g.preClose[stock] = price.iloc[0]['close']
    if g.security:
        subscribe(g.security, 'tick')
    if g.dragonLeader:
        print('拿着龙头：%s' %str(g.dragonLeader))
    
## 收盘后运行函数
def after_market_close(context):
    # 取消今天订阅的标的
    unsubscribe_all()
    #得到当天所有成交记录
    trades = get_trades()
    for _trade in trades.values():
        log.info('成交记录：'+str(_trade))
    log.info('一天结束')
    log.info('##############################################################')

#是否是次新股
def isNew(context, code):
    IpoDate = get_security_info(code).start_date
    IpoDays = context.current_dt-datetime.datetime.strptime(str(IpoDate),'%Y-%m-%d')
    if IpoDays.days<100:
        return True
    return False

# 有tick事件时运行函数
'''
一个 tick 所包含的信息。 tick 中的信息是在 tick 事件发生时， 盘面的一个快照。
code: 标的的代码
datetime: tick 发生的时间
current: 最新价
open：当日开盘价
high: 截至到当前时刻的最高价
low: 截至到当前时刻的最低价
volume: 截至到当前时刻的成交量
money: 截至到当前时刻的成交额
position: 截至到当前时刻的持仓量，只适用于期货 tick 对象
a1_v ~ a5_v: 卖一量到卖五量，对于期货，只有卖一量
a1_p ~ a5_p: 卖一价到卖五价，对于期货，只有卖一价
b1_v ~ b5_v: 买一量到买五量，对于期货，只有买一量
b1_p ~ b5_p: 买一价到买五价，对于期货，只有买一价
'''
def handle_tick(context, tick):
    if g.security:
        hitBoard(context, tick)
    if context.portfolio.positions:
        sell(context,tick)

def hitBoard(context, tick):
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    if hour==9 and minute<30:
        return
    if hour>=14 and minute>=30:
        return
    stock = tick.code 
    current_data = get_current_data()   
    highLimit = current_data[stock].high_limit
    dayOpen = round(current_data[stock].day_open,2)
    #封单额大于1500万就不买了
    if tick.b1_v > 15000000/highLimit:
        return
    # 取得当前的现金
    cash = context.portfolio.available_cash
    nowPrice = round(tick.current,2)

    #之前的滑点买入还是不太行，现在改成委卖试试
    #4种买入情况：1、买一是涨停价即将封死；其余3种是卖1到卖3还有挂单
    if tick.b1_p == highLimit or tick.a1_p == highLimit or tick.a2_p == highLimit \
    or (nowPrice < 10 and tick.a3_p == highLimit):
        portfolio = context.portfolio
        positions = context.portfolio.positions
        #开板回封买回只买一半：当天涨停开盘且没开仓，而且持仓已经卖光
        if stock in g.positions and stock not in positions and cash > highLimit*200:
            tickPrice = get_ticks(stock, start_dt=context.current_dt.strftime("%Y-%m-%d"), \
            end_dt=tick.datetime, fields=['time', 'current'])   
            trades = get_trades()
            amount = 0
            for trade in trades.values():
                if stock == trade.security:
                    amount += trade.amount
            #目前样本统计看买回1/2效果是最好的
            if dayOpen == highLimit:
                #一字板开板补量时间一般很短，为了拿下这个买点就得缩短开板时间要求
                #如果当前已经涨停，这个判断就失效，所以要把当前这个tick移除，从倒数第二个开始
                #当天没涨停过，那肯定不能买
                if round(max(tickPrice['current'].tolist()[-3:-1]),2) != highLimit\
                and round(max(tickPrice['current'].tolist()[:-1]),2) == highLimit:
                    if highLimit/min(tickPrice['current'].tolist()[:-1])>1.05:
                        print('一字开板回封全部买回->'+stock)
                        order_target(stock, int(trade.amount), style=LimitOrderStyle(highLimit))        
                    else:
                        print('一字开板回封买回1/2->'+stock)
                        order_target(stock, int(trade.amount/2), style=LimitOrderStyle(highLimit))    
            else:
                #如果当前已经涨停，这个判断就失效，所以要把当前这个tick移除，从倒数第二个开始
                #当天没涨停过，那肯定不能买
                if round(max(tickPrice['current'].tolist()[-11:-1]),2) != highLimit\
                and round(max(tickPrice['current'].tolist()[:-1]),2) == highLimit:                
                    print('自然板开板回封买回1/2->'+stock)
                    order_target(stock, int(trade.amount/2), style=LimitOrderStyle(highLimit))
         #T字板买入
        if dayOpen==highLimit:            
            if hour==9 and minute==30 and context.current_dt.second < 30:
                return  
            #统计当天最低价
            barCnt = (hour-9)*4+int(minute/15)
            barsOf15Min = get_bars(tick.code, barCnt, unit='15m',fields=['low'],include_now=True)
            dayLow = min(barsOf15Min['low'])
            #开板时间要大于30秒
            tickPrice = get_ticks(stock,end_dt=tick.datetime, count=10, fields=['time', 'current'])   
            if round(max(tickPrice['current'].tolist()),2) == highLimit:
                return
            #开板跌幅小于1%，不考虑。如果开板后跌幅大于1%，现在又回到了涨停价，那么可以买
            if dayLow>highLimit*0.99:
                return
        #positions是最新持仓，g.positions是开盘前持仓，为了防止卖出后继续买入，要区别对待
        if stock not in positions and stock not in g.positions \
        and cash > highLimit*100:
            print('买入->'+stock)
            order_value(stock, cash, style=LimitOrderStyle(highLimit))
            '''if  portfolio.available_cash < portfolio.total_value*0.4: 
                print('all in-----------------------')
                order_value(stock, portfolio.available_cash)
            else:
                print('buy 1/2--------------------------')
                order_value(stock, portfolio.available_cash/2)'''
    return

'''
卖出策略
1、涨停开盘：
1.1、开板卖，回封买回1/2
2、非涨停开盘：
2.1、9:31出现5+%拐点 卖
2.2、5以下拐点，10:30点前杀到-8卖，10:30后还是绿的卖
2.3、开板卖，回封买回1/3
2.4、最高点跌幅超过10卖
2.5、止盈：20%止盈3成和30%止盈3.5成
2.6、开板卖，回封买回1/3
2.7、收盘不涨停卖
'''
def sell(context, tick):
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    stock = tick.code
    if hour==9 and minute<30:
        return
    curPositions = context.portfolio.positions
    if len(curPositions) == 0 or tick.code not in curPositions\
     or curPositions[stock].closeable_amount<=0:
        return
    currentData = get_current_data()
    highLimit = currentData[stock].high_limit
    lowLimit = currentData[stock].low_limit
    dayOpen =  currentData[stock].day_open
    avgCost = curPositions[stock].avg_cost
    nowPrice = round(tick.current,2)
    
    #跌停没法卖
    if nowPrice == lowLimit or nowPrice == highLimit:
        return
    if dayOpen != highLimit:
        stopWin(tick, curPositions)
        
        if nowPrice >= g.preClose[stock]*1.05:
            sellIf931NotRushUp(hour, minute, tick, dayOpen)
        sellIfDown10pct(tick, hour, minute)
        #stop loss
        if  nowPrice <= avgCost*0.92 or nowPrice <= g.preClose[stock]*0.92:
            print('跌幅超过-8%卖'+stock)
            order_target(stock, 0)
        is1030to1100 = hour == 10 and minute >= 00
        isLaterThan1030 = is1030to1100 or hour >= 11
        if isLaterThan1030 and nowPrice <= g.preClose[stock]:
            print('10:30后绿的卖'+stock)
            order_target(stock, 0)
    sellIfNotBoard(tick, hour, minute, highLimit)
    sellIfBoardOpened(tick, highLimit)

#止盈方法，每天只能止盈一次
def stopWin(tick, position):
    trades = get_trades()
    stock = tick.code
    nowPrice = round(tick.current,2)
    for trade in trades.values():
        if stock == trade.security:
            return
    if nowPrice >= position[stock].avg_cost*1.43:
        print('止盈43%卖'+stock)
        #卖一半
        order_target(stock, int(position[stock].closeable_amount*0.5))
        return
    if nowPrice >= position[stock].avg_cost*1.328:
        print('止盈32%卖'+stock)
        #卖一半
        order_target(stock, int(position[stock].closeable_amount*0.5))
        return
    
    if nowPrice >= position[stock].avg_cost*1.208:
        print('止盈20%卖'+stock)
        #卖3成留7成
        order_target(stock, int(position[stock].closeable_amount*0.7))
        print(get_trades())

#9:31没有往上冲卖        
def sellIf931NotRushUp(hour, minute, tick, dayOpen):
    if hour == 9 and minute == 31 and tick['current']<dayOpen*1.02:
        print('9:31没有往上冲卖'+tick.code)
        order_target(tick.code, 0)

#拐头卖
def sellIfTurnDown(tick):
    tickPrice = get_ticks(tick.code,end_dt=tick.datetime, count=40, fields=['time','current'])
    curTicks = tickPrice['current']
    packedTicks = []
    for i in range(len(curTicks)):
        if i%9 == 0:
            packedTicks.append(curTicks[i])
    lenOfTicks = len(packedTicks)
    if lenOfTicks>0 and packedTicks[lenOfTicks-1]<0.98*packedTicks[lenOfTicks-2]:
        print('拐头卖'+str(tick.code))
        order_target(tick.code, 0)

#开板卖
def sellIfBoardOpened(tick, highLimit):
    tickPrice = get_ticks(tick.code,end_dt=tick.datetime, count=2, fields=['time','current'])
    curTicks = tickPrice['current']
    if curTicks[1] < curTicks[0] and round(curTicks[0],2) == highLimit:
        print('开板卖'+str(tick.code))
        order_target(tick.code, 0)

#绿盘卖
def sellIfGreen(tick):
    if tick.current<g.preClose[tick.code]:
        print('绿盘卖'+str(tick.code))
        order_target(tick.code, 0)

#收盘不板卖
def sellIfNotBoard(tick, hour, minute, high_limit): 
    if hour==14 and minute==55 and round(tick.current,2) != high_limit:
        print('收盘不涨停卖'+str(tick.code))
        order_target(tick.code, 0)

#最高点跌幅超过10%卖
def sellIfDown10pct(tick, hour, minute):
    #统计当天最低价
    barCnt = (hour-9)*4+int(minute/15)
    barsOf15Min = get_bars(tick.code, barCnt, unit='15m',fields=['high'],include_now=True)
    dayHigh = max(barsOf15Min['high'])
    if tick.current < dayHigh*0.9:
        print('最高点跌幅超过10%卖'+str(tick.code))
        order_target(tick.code, 0)

'''
--------------------------------数据统计区BEGIN----------------------------------
'''

#是否是一字板
def isYZB(data, i):
    if data.iloc[i]['high_limit'] == data.iloc[i]['low'] \
    and data.iloc[i]['close']/data.iloc[i-1]['close'] > 1.09:
        return True
    return False

#是否是涨停
def isUpLimit(data, i):
    if data.iloc[i]['high_limit'] == data.iloc[i]['close']\
    and data.iloc[i]['close']/data.iloc[i-1]['close'] > 1.09 :
        return True
    return False


#计算涨停数，加上中继涨停，只要中间不涨停的K线是红的，就可以一直连下去
def countUpLimit(data, day, stock):
    #最后一条数据索引
    lastIndex = data.shape[0]-1
    if not isUpLimit(data, lastIndex):
        return 0
    i = lastIndex
    upLimitCnt = 0
    notBoardTimes = 0
    while i >= 0:
        if isUpLimit(data, i):
            upLimitCnt += 1
        elif isUpLimit(data, i-1):
            if data.iloc[i]['close'] < data.iloc[i-1]['close'] *0.95:
                break
        else:
            break
        i -= 1
    return upLimitCnt

#计算最大值所在列，也就是股票代码        
def calcMaxIndex(row):#对每一行处理的函数
    maxValues = row[row==row['highestBoard']].dropna(how='all')
    codes = maxValues.index.tolist()
    codes.remove('highestBoard')
    row['code'] = codes
    return row

#格式化tushare日期为聚宽格式
def formatTSDateToJoint(data):
    for i in range(len(data)):
        item = data[i]
        data[i] = item[0:4]+'-'+item[4:6]+'-'+item[6:8]
    return data

def formatDate(data):
    for i in range(len(data)):
        data[i] = data[i].strftime("%Y-%m-%d")
        
    return data

def formatTuShareCode(data):
    for i in range(len(data)):
        item = data[i]
        if 'SH' in item:
            data[i] = item.replace('SH', 'XSHG')
        else:
            data[i] = item.replace('SZ', 'XSHE')
    return data

#cnt 连板数
def addStockData(continuousBoard, day, stock, cnt):
    if stock not in continuousBoard.columns:
        continuousBoard[stock] = [0]*continuousBoard.shape[0]
    continuousBoard.loc[day, stock] = cnt
    return continuousBoard

#依赖仓位
#计算当前周期的最高龙头，可称为周期龙，可能不是当天的连板龙头，就用板数做高度吧以后也可以看看用连板期间涨幅
def calcPeriodDragon(continuousBoard):
    continuousBoard['periodDragon'] = ['']*continuousBoard.shape[0]
    for i in range(1, continuousBoard.shape[0]):
        date = continuousBoard.index.tolist()[i]
        periodStart = continuousBoard[continuousBoard.position=='多多多'].index.tolist().tail(1)
        thisPeriod = continuousBoard['highestBoard', 'code'][periodStart:i]
        continuousBoard.loc[date, 'periodDragon'] = continuousBoard.iloc[i-1]['code']
    return continuousBoard

'''
#依赖周期龙头
计算市场强度（开盘竞价的强度自己扫一下周期龙就行了，这里是回测用）
周期龙竞价超过-5说明开始退潮，-7说明结束竞价清仓
周期龙竞价在-5以上，可以不用管，看昨天的高度龙
如果是放在策略里面，这个方法开盘后算一次，后面每隔一分钟计算一次，动态反应强度的变化
'''
def calcPeriodStrength(continuousBoard):
    continuousBoard['openStrength'] = [0]*continuousBoard.shape[0]
    continuousBoard['closeStrength'] = [0]*continuousBoard.shape[0]
    #周期信号
    continuousBoard['periodSignal'] = [0]*continuousBoard.shape[0]
    for i in range(1, continuousBoard.shape[0]):
        dragons = continuousBoard.iloc[i]['code']
        #如果当天存在多个龙头，说明行情还在半路，强度就算平均得了
        startDate = continuousBoard.index.tolist()[i-1]
        endDate = continuousBoard.index.tolist()[i]
        openStrength = 0
        closeStrength = 0
        if len(dragons) > 1:
            for stock in dragons:
                price = get_price(stock, start_date=startDate, end_date=endDate, \
                                 frequency='daily', fields=['open','close','high','high_limit'], \
                                 fq='pre')    
                if price.empty or price.shape[0]!=2:
                    continue
                openStrength = (price.iloc[1]['open']/price.iloc[0]['close']-1)*100
                downStart = price.iloc[0]['close']
                '''if price.iloc[1]['open'] > price.iloc[0]['close']:
                    downStart = price.iloc[1]['open']
                if price.iloc[1]['high'] == price.iloc[1]['hight_limit']:
                    downStart = price.iloc[1]['high']'''
                closeStrength = (price.iloc[1]['close']/downStart-1)*100
                if openStrength < continuousBoard.loc[endDate, 'openStrength']:
                    continuousBoard.loc[endDate, 'openStrength'] = openStrength
                if closeStrength < continuousBoard.loc[endDate, 'closeStrength']:
                    continuousBoard.loc[endDate, 'closeStrength'] = closeStrength
        elif len(dragons) == 1:
            price = get_price(dragons[0], start_date=startDate, end_date=endDate, \
                             frequency='daily', fields=['open','close','high','high_limit'],\
                             skip_paused=True, fq='pre')    
            if price.empty or price.shape[0]!=2:
                continue
                openStrength = (price.iloc[1]['open']/price.iloc[0]['close']-1)*100
                downStart = price.iloc[0]['close']
                '''if price.iloc[1]['open'] > price.iloc[0]['close']:
                    downStart = price.iloc[1]['open']
                if price.iloc[1]['high'] == price.iloc[1]['hight_limit']:
                    downStart = price.iloc[1]['high']'''
                closeStrength = (price.iloc[1]['close']/downStart-1)*100
            continuousBoard.loc[endDate, 'openStrength'] = openStrength
            continuousBoard.loc[endDate, 'closeStrength'] = closeStrength
    return continuousBoard

#给市场强度进行强度划分：极弱等杀到3板或者以下结束周期干
#竞价弱当天不能干等结束后看当天情绪，收盘还是弱第二天不能干；正常就是干
def ratePeriodStrenth(continuousBoard):
    continuousBoard['periodRate'] = ['']*continuousBoard.shape[0]
    for i in range(1, continuousBoard.shape[0]):
        date = continuousBoard.index.tolist()[i]
        if continuousBoard.iloc[i]['closeStrength'] <= -15:
            continuousBoard.loc[date, 'strengthRate'] = '极弱'
        elif continuousBoard.iloc[i]['closeStrength'] <= -5:
            continuousBoard.loc[date, 'strengthRate'] = '弱'
        else:
            continuousBoard.loc[date, 'strengthRate'] = '正常'
    return continuousBoard

'''
牛市：30天涨幅超25%，40天超30%；强市：40天涨幅超25%，60天超30%；熊市：30天跌幅超10%；其它是震荡市
'''
def calcMarketStrength(continuousBoard):
    continuousBoard['marketRate'] = ['']*continuousBoard.shape[0]
    for i in range(continuousBoard.shape[0]):
        endDate = continuousBoard.index.tolist()[i]
        prices = get_price('000001.XSHG', count = 60, end_date=endDate,  \
                            frequency='daily', fields=['open', 'low', 'close', 'high_limit'], \
                           skip_paused=True, fq='pre')
        hisClose = prices['close']
        changePctOf30 = max(hisClose[-30:]) / min(hisClose[-30:])
        changePctOf40 = max(hisClose[-40:]) / min(hisClose[-40:])
        changePctOf60 = max(hisClose[-60:]) / min(hisClose[-60:])
        if changePctOf30 >= 1.25 or changePctOf40 >= 1.3:
            #牛市
            continuousBoard.loc[endDate, 'marketRate'] = '牛市'
        elif changePctOf40 >= 1.25  or changePctOf60 >= 1.3:
            #强市
            continuousBoard.loc[endDate, 'marketRate'] = '强市'
        elif changePctOf30 <= 0.9:
            #熊市
            continuousBoard.loc[endDate, 'marketRate'] = '熊市'
        else:
            #震荡市
            continuousBoard.loc[endDate, 'marketRate'] = '震荡市'

#依赖市场强度
#计算仓位，目前只有满仓和空仓，龙头跌停隔日空仓，新龙头继续跌停等见底 
#空空空是周期结束标志，在新周期开始的多多多信号出现之前不能开仓
def calcPosition(continuousBoard):
    continuousBoard['position'] = ['']*continuousBoard.shape[0]
    for i in range(2, continuousBoard.shape[0]):
        date = continuousBoard.index.tolist()[i]
        marketRate = continuousBoard['marketRate'].tolist()
        #默认震荡市3板
        lowestBoard = 3
        #牛市、强市、熊市信号的作用时间最少是2个月
        startIndex = -40
        if i < 40:
            startIndex = 0
        marketRate = marketRate[startIndex:i]
        if '牛市' in marketRate or '强市' in marketRate:
            lowestBoard = 4
        elif '熊市' in marketRate:
            lowestBoard = 2
        if continuousBoard.iloc[i]['highestBoard'] >= 5 \
        and continuousBoard.iloc[i-1]['closeStrength'] == -10:
            continuousBoard.loc[date, 'position'] = '空'
            if continuousBoard.iloc[i-2]['closeStrength'] == -10:
                continuousBoard.loc[date, 'position'] = '空空空'
        if continuousBoard.iloc[i]['highestBoard'] >= lowestBoard \
        and '空空空' in continuousBoard['position'][-5:].tolist():
                continuousBoard.loc[date, 'position'] = '空'
        #如果不是空，那就是多
        if '空' not in continuousBoard.iloc[i]['position']:
            continuousBoard.loc[date, 'position'] = '多'
        if continuousBoard.iloc[i-1]['highestBoard'] == lowestBoard \
        and continuousBoard.iloc[i]['highestBoard'] <= lowestBoard:
            continuousBoard.loc[date, 'position'] = '多多多'
        if continuousBoard.iloc[i]['highestBoard'] < lowestBoard:
            continuousBoard.loc[date, 'position'] = '多多多'

#计算当天要打板的股票池
def calcStocksToHit(continuousBoard):
    continuousBoard['stockPool'] = ['']*continuousBoard.shape[0]
    for i in range(continuousBoard.shape[0]):
        date = continuousBoard.index.tolist()[i]
        marketRate = continuousBoard['marketRate'].tolist()
        #默认震荡市3板
        lowestBoard = 3
        #牛市、强市、熊市信号的作用时间最少是2个月
        startIndex = -50
        if i < 50:
            startIndex = 0
        marketRate = marketRate[startIndex:i]
        if '牛市' in marketRate or '强市' in marketRate:
            lowestBoard = 4
        elif '熊市' in marketRate:
            lowestBoard = 2
        lowestBoard -= 1  #打N板得选N-1的板
        
        rowData = continuousBoard.iloc[i]  #注意是前一天的数据
        removeRowString(rowData)
        rowData = rowData.sort_values(ascending=False)
        stockPool = []
        for stock,boards in rowData.iteritems():
            if rowData[stock] > lowestBoard:
                continue
            if rowData[stock] < lowestBoard:
                break
            if  checkChip(stock, date):
                stockPool.append(stock)
        continuousBoard.loc[date, 'stockPool'] = str(stockPool)

            
#检查筹码，有套牢盘的返回False，否则返回True 
#计算2-3板价格在过去100天的K线包含数（最高最低）大于多少pass，1个月内出现直接pass，2板时20日涨幅大于多少pass
#上市天数小于100天=5个月pass
def checkChip(stock, endDate):
    IpoDate = get_security_info(code).start_date
    IpoDays = endDate-datetime.datetime.strptime(str(IpoDate),'%Y-%m-%d')
    if IpoDays < 100:
        return False
    prices = get_price(stock, end_date=endDate, count = 100, \
                     frequency='daily', fields=['high', 'low', 'close', 'high_limit'],\
                     skip_paused=True, fq='pre')
    if prices.iloc[prices.shape[0]-1]['close']/min(prices[-20:]['close'].tolist()) > 1.4:
        print(stock+'涨幅超过40%被过滤')
        return False
    Tday = prices.tail(1)
    TdayHigh = prices.iloc[prices.shape[0]-1]['high']
    TdayLow = prices.iloc[prices.shape[0]-1]['low']
    for i in range(prices.shape[0]-20, prices.shape[0]-1):
        high = prices.iloc[i]['high']
        low = prices.iloc[i]['low']
        #三种碰撞情况
        upCollide = TdayHigh > high and TdayLow < high
        innnerCollide = TdayHigh <  prices.iloc[i]['high'] and TdayLow >  prices.iloc[i]['low']
        downCollide = TdayHigh <  prices.iloc[i]['high'] and TdayLow < prices.iloc[i]['low']
        if upCollide or innnerCollide or downCollide:
            return False
    collideCnt = 0
    for i in range(prices.shape[0]-1):
        #三种碰撞情况
        upCollide = TdayHigh > prices.iloc[i]['high'] and TdayLow < prices.iloc[i]['high']
        innnerCollide = TdayHigh <  prices.iloc[i]['high'] and TdayLow >  prices.iloc[i]['low']
        downCollide = TdayHigh <  prices.iloc[i]['high'] and TdayLow < prices.iloc[i]['low']
        if upCollide or innnerCollide or downCollide:
            collideCnt += 1
            if collideCnt > 10:
                return False
    return True

def removeRowString(rowData):
    rowData.pop('code')
    rowData.pop('highestBoard')
    rowData.pop('position')
    rowData.pop('marketRate')
    rowData.pop('stockPool')

def prepareData(endDate):
    print('-------------开始统计数据-------------')
    #初始化tushare
    pro = ts.pro_api()
    #开始统计日期
    startDate = (endDate+datetime.timedelta(days=-70)).strftime("%Y-%m-%d")
    
    #由于聚宽的接口不能没有提供上交所，深交所的交易日期数据，所以使用tushare的
    #机智得使用指数行情来获取交易日期^_^
    tradeDates = get_price('000001.XSHG', start_date=startDate, end_date=endDate, \
                         frequency='daily', fields=['open', 'low', 'close', 'high_limit'],\
                         skip_paused=True, fq='pre')
    indexPrice = tradeDates['close'].tolist()
    tradeDates = tradeDates.index.tolist()
    tradeDates = formatDate(tradeDates)
    #连板统计结果
    continuousBoard = pd.DataFrame([], index=tradeDates)
    
    for i in range(30, len(tradeDates)):
        #-----------统计当天最高的连板天数----------------------
        dayProcessTime = time.clock()
        day = tradeDates[i]
        countUpLimitTime = 0
        cnt = 0
        if '399001.XSHE' not in continuousBoard.columns:
            continuousBoard['399001.XSHE'] = [0]*continuousBoard.shape[0]
        continuousBoard.loc[day, '399001.XSHE'] = 1
        tsDay = str(day)
        tsDay = tsDay[0:4]+tsDay[5:7]+tsDay[8:10]
        allPriceData = pro.daily(trade_date = tsDay)
        upLimitData = allPriceData[allPriceData.pct_chg>=9.9] #当天涨停数据
        stocks = upLimitData['ts_code'].tolist()
        stocks = formatTuShareCode(stocks) #把涨停个股代码转换成聚宽格式
        for stock in stocks:
            #获取历史行情，如果有停牌，那么这个startDate就不能这么取，默认多取20条，
            #也就是停牌超过10交易日很可能就没法统计了
            startDate = tradeDates[0]
            if tradeDates.index(day) > 30:
                startDate = tradeDates[tradeDates.index(day)-30]
            historyPrice = get_price(stock, start_date=startDate, end_date=day, \
                                     frequency='daily', fields=['open', 'low', 'close', 'high_limit'],\
                                     skip_paused=True, fq='pre')
            #如果提前15天取数据不够10条，那么说明停牌时间过长，不在考虑范围
            #这样也可以过滤开板新股
            if historyPrice.shape[0] < 25:
                continue
            latestRow = historyPrice.tail(1)
            #如果最新一条数据不是当天数据，那么是停牌，不统计
            if day not in latestRow.index:
                continue
            #计算每天个股的连板数
            cnt = countUpLimit(historyPrice, day, stock)
            if cnt >= 1:
                addStockData(continuousBoard, day, stock, cnt)
        remainingTime = (time.clock()-dayProcessTime)*(len(tradeDates)-i)
        remainingTime = remainingTime/60
        dayProcessTime = time.clock()-dayProcessTime
        progress = ((i-29)/(len(tradeDates)-30))*100
        if round(progress)%5 == 0:
            print('统计进度>>%d%%  预计还需>>%.2f分钟' % (progress,remainingTime))
    
    
    #计算每天的最高连板数
    continuousBoard = continuousBoard[continuousBoard>=1]    
    continuousBoard = continuousBoard.dropna(axis=0, how='all')  
    continuousBoard = continuousBoard.dropna(axis=1, how='all') 
    continuousBoard = continuousBoard.fillna(0)
    continuousBoard['highestBoard'] = continuousBoard.max(axis=1)
    continuousBoard = continuousBoard.apply(lambda x:calcMaxIndex(x),axis=1)
    #由于上面公式添加列名之后没有新加列名字，默认为0，所以要替换掉最后一个列名
    cols = continuousBoard.columns.tolist()
    cols[len(cols)-1] = 'code'
    continuousBoard.columns = cols
    
    
    calcPeriodStrength(continuousBoard)
    calcMarketStrength(continuousBoard)
    calcPosition(continuousBoard)
    calcStocksToHit(continuousBoard)
    
    return continuousBoard
'''
--------------------------------数据统计区END--------------------------------------------
'''

