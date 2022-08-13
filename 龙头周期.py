from jqdata import finance 
from pylab import mpl
from matplotlib.ticker import  MultipleLocator
import pandas as pd
import warnings
import numpy as np
import datetime
import matplotlib.pyplot as plt
import time
import tushare as ts
import math
from mpl_toolkits.axisartist.parasite_axes import HostAxes, ParasiteAxes
#from jqdatasdk import *
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication 
import smtplib


#初始化tushare
ts.set_token('d36d566f61ff364b5b6824484426752e1bbbe092dfaaec2d9c2cd996')
pro = ts.pro_api()
#过滤警告信息
#warnings.filterwarnings("ignore")

#是否是一字板
def isYZB(data, i):
    if data.iloc[i]['high_limit'] == data.iloc[i]['low'] \
    and data.iloc[i]['close']/data.iloc[i-1]['close'] > 1.08:
        return True
    return False

#是否是T字板
def isTBoard(data, i):
    if data.iloc[i]['high_limit'] != data.iloc[i]['low'] \
    and data.iloc[i]['open'] == data.iloc[i]['close'] \
    and data.iloc[i]['close']/data.iloc[i-1]['close'] > 1.08:
        return True
    return False

#是否是涨停
def isUpLimit(data, i):
    if data.iloc[i]['high_limit'] == data.iloc[i]['close']\
    and data.iloc[i]['close']/data.iloc[i-1]['close'] > 1.09 :
        return True
    return False


#计算涨停数，加上中继涨停，只要中间不涨停的K线是红的，就可以一直连下去
#canJoin，可以连接断板
def countUpLimit(data, day, stock, canJoin):
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
        elif not canJoin:
            break
        elif isUpLimit(data, i-1):
            if data.iloc[i]['close'] < data.iloc[i-1]['close'] *0.95\
            or data.iloc[i-1]['close'] < data.iloc[i-2]['close'] *0.95:
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
        startIndex = -50
        if i < 50:
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
        and continuousBoard.iloc[i]['highestBoard'] == lowestBoard:
            continuousBoard.loc[date, 'position'] = str(lowestBoard) + '板放开打'
        if continuousBoard.iloc[i]['highestBoard'] < lowestBoard:
            continuousBoard.loc[date, 'position'] = str(lowestBoard) + '板放开打'

#计算当天可以给明天打板的股票池
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
        
        rowData = continuousBoard.iloc[i] 
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
#计算2-3板价格在过去100天的K线包含数（最高最低）大于10pass，1个月内出现直接pass
#2板时20日涨幅大于40%pass 4个月跌幅超过40%免检
#前2板没有一字板且2天成交量小于1.5亿的庄股拉黑，这种庄股是炸板超级回撤的根源
def checkChip(stock, endDate):
    IpoDate = get_security_info(stock).start_date
    IpoDays = datetime.datetime.strptime(endDate,'%Y-%m-%d')\
            -datetime.datetime.strptime(str(IpoDate),'%Y-%m-%d')
    if IpoDays.days < 100:
        return False
    prices = get_price(stock, end_date=endDate, count = 100, \
                     frequency='daily', fields=['high', 'low', 'close', 'high_limit', 'money'],\
                     skip_paused=True, fq='pre')
    if prices.iloc[prices.shape[0]-1]['close']/min(prices[-20:]['close'].tolist()) > 1.4:
        return False
    if min(prices[-20:]['close'].tolist()) / max(prices[:20]['close'].tolist()) < 0.6:
        return True
    
    if (prices.iloc[prices.shape[0]-1]['high_limit'] != prices.iloc[prices.shape[0]-1]['low'] or \
        prices.iloc[prices.shape[0]-2]['high_limit'] != prices.iloc[prices.shape[0]-2]['low']) and \
        (prices.iloc[prices.shape[0]-1]['money']+prices.iloc[prices.shape[0]-2]['money'])<150000000:
        return False
    
    #只把套牢区锁定在三板的5-10%
    TdayHigh = prices.iloc[prices.shape[0]-1]['close']*1.1
    TdayLow = prices.iloc[prices.shape[0]-1]['close']*1.05
    for i in range(prices.shape[0]-30, prices.shape[0]-1):
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


def isNew(day, code):
    info = get_security_info(code)
    if info is None:
        return True
    IpoDate = get_security_info(code).start_date
    IpoDays = datetime.datetime.strptime(str(day),'%Y-%m-%d')\
    -datetime.datetime.strptime(str(IpoDate),'%Y-%m-%d')
    #自然日，要算假期
    if IpoDays.days < 42:
        return True
    return False    

def sendEmail(version):
    fromaddr = ''
    password = ''
    toaddrs = []

    content = '九阳真经日报' + version
    textApart = MIMEText(content)

    imageFile = './output/九阳真经.png'
    imageApart = MIMEImage(open(imageFile, 'rb').read(), imageFile.split('.')[-1])
    imageApart.add_header('Content-Disposition', 'attachment', filename='九阳真经.png')
    
    m = MIMEMultipart()
    m.attach(textApart)
    m.attach(imageApart)
    m['Subject'] = datetime.datetime.now().strftime("%Y-%m-%d") + '九阳真经日报' 
    m['From'] = fromaddr
  

    try:
        server = smtplib.SMTP()
        server.connect('smtp.qq.com', 587)
        server.login(fromaddr,password)
        server.sendmail(fromaddr, toaddrs, m.as_string())
        print('邮件发送成功')
        server.quit()
    except smtplib.SMTPException as e:
        print('error:',e) #打印错误     


'''
---------------------------------------业务逻辑区BEGIN-------------------------------------------------------
'''

#canJoin能否连接断板
def calcDataAndDraw(canJoin):
    print('\n-------------开始统计数据-------------')
    #开始统计日期
    startDate = '2019-05-01'
    startDate = (datetime.datetime.now()+datetime.timedelta(days=-100)).strftime("%Y-%m-%d")
    #结束统计日期
    endDate = '2020-03-01'
    endDate = (datetime.datetime.now()+datetime.timedelta(days=0)).strftime("%Y-%m-%d")


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
        upLimitData = allPriceData[allPriceData.pct_chg>=9.8] #当天涨停数
        stocks = upLimitData['ts_code'].tolist()
        if len(stocks) == 0:
            break
        stocks = formatTuShareCode(stocks) #把涨停个股代码转换成聚宽格式
        for stock in stocks:
            #获取历史行情，如果有停牌，那么这个startDate就不能这么取，默认多取20条，
            #也就是停牌超过10交易日很可能就没法统计了
            #剔除新股
            if(isNew(day, stock)):
                continue
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
            cnt = countUpLimit(historyPrice, day, stock, canJoin)
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


    print('---------------------数据准备就绪，开始制图--------------------------')

    #绘制指数图
    #Y轴最大最小值
    maxContLimit = max(continuousBoard['highestBoard'].tolist())+1
    minContLimit = min(continuousBoard['highestBoard'].tolist())-1
    figsizeX = continuousBoard.shape[0]*3.2
    figsizeY = (maxContLimit-minContLimit)*2.5

    mpl.rcParams.update({'font.size': 16})
    mpl.rcParams['font.sans-serif'] = ['SimHei']
    mpl.rcParams['axes.unicode_minus'] = False # 解决保存图像是负号'-'显示为方块的问题,或者转换负号为字
    dates = continuousBoard.index.tolist()
    x = np.arange(len(dates))
    startIndex = len(indexPrice)-continuousBoard.shape[0]
    periodIndexPrices = indexPrice[startIndex:]
    periods = continuousBoard['highestBoard'].tolist()
    maxIndexPrice = max(periodIndexPrices)+30
    minIndexPrice = min(periodIndexPrices)-30

    fig, axPeriod = plt.subplots() 
    fig.set_figwidth(figsizeX)
    fig.set_figheight(figsizeY)
    axPeriod.plot(x, periods, 'r*-', ms=25, label='连板数')
    axPeriod.set_xticks(x)
    axPeriod.set_xticklabels(dates)
    axPeriod.set_xlabel("日期")
    axPeriod.set_ylabel("连板数")
    axPeriod.set_ylim(minContLimit, maxContLimit)
    for xtick in axPeriod.get_xticklabels():
        xtick.set_rotation(50)
    plt.legend(loc='upper right') 

    axIndex = axPeriod.twinx()
    axIndex.plot(x, periodIndexPrices, 'o-', label='上证指数')
    axIndex.set_ylabel("上证指数")
    axIndex.set_ylim(minIndexPrice, maxIndexPrice)
    plt.legend(loc='lower right')

    #面霸统计
    noodleKings = []
    noodleKingCnt = 0

    for i in range(1, continuousBoard.shape[0]):
        #最高板BEGIN
        #这里是统计今天的龙头，所以用今天的数据
        rowData = continuousBoard.iloc[i]
        codes = rowData['code']
        if len(codes) > 7:
            stockName = '>>>>>龙头['+str(len(codes))+']<<<<<'
        else:
            stockName = '>>>>>龙  头<<<<<'
        startDate = continuousBoard.index.tolist()[i-1]
        endDate = continuousBoard.index.tolist()[i]

        for j in range(len(codes)):
            if j > 9:
                break
            if '399001' in codes[j]:
                continue
            stockName += '\n'
            stock = codes[j]
            stockName +=  get_security_info(stock).display_name
            price = get_price(stock, start_date=startDate, end_date=endDate, \
                                     frequency='daily', fields=['open','close','high','high_limit', 'low'],\
                                     skip_paused=True, fq='pre')    
            if price.empty or price.shape[0]!=2:
                continue
            isYZ = isYZB(price, 1)
            if isYZ:
                stockName += '[一]'
            else:
                openStrength = (price.iloc[1]['open']/price.iloc[0]['close']-1)*100
                lowStrength = (price.iloc[1]['low']/price.iloc[0]['close']-1)*100
                stockName += str('({:.0f},{:.0f})%').format(openStrength, lowStrength)
        #连板数   ----------------------------
        contLimit = rowData['highestBoard']
        xTextPos = i  #x轴文字位置
        yTextPos = contLimit  #y轴文字位置
        
        if yTextPos >= 7:
            yTextPos = yTextPos/2
            xTextPos += 0.05
        elif yTextPos >= 5:
            yTextPos = yTextPos- 2
            xTextPos += 0.05
        elif yTextPos == 1:
            yTextPos = 1.3
        else:
            yTextPos += 0.3
        if i == continuousBoard.shape[0]-1:
            xTextPos = i+0.15
        elif i == 0:
            xTextPos = i+0.15
        stockName += '['+str(int(contLimit))+']'
        #最高板END

        #中军BEGIN
        rowData = continuousBoard.iloc[i]  #注意是前一天的数据
        removeRowString(rowData)
        rowData = rowData.sort_values(ascending=False)
        minMidCont = 2 #中军最低板
        midArmyCnt = 0
        midArmyStokcs = '' #临时存放用来计算掉队
        for stock,boards in rowData.iteritems():
            midArmyStokcs += stock
            if rowData[stock] < minMidCont:
                break
            if '399001' in codes[j]:
                    continue
            name = get_security_info(stock).display_name
            if name not in stockName:
                if midArmyCnt > 19:
                    continue
                if len(name) == 3:
                    name += '   '
                if 'ST' in name:
                        name += ' '
                if '中 军' not in stockName:    
                    stockName += '\n>>>>>中 军<<<<<'
                #计算强度
                stockName += '\n' + name
                price = get_price(stock, start_date=startDate, end_date=endDate, \
                                     frequency='daily', fields=['open','close','high','high_limit', 'low'],\
                                     skip_paused=True, fq='pre')    
                if price.empty or price.shape[0]!=2:
                    continue
                isYZ = isYZB(price, 1)
                if isYZ:
                    stockName += '[一]'
                else:
                    openStrength = (price.iloc[1]['open']/price.iloc[0]['close']-1)*100
                    lowStrength = (price.iloc[1]['low']/price.iloc[0]['close']-1)*100
                    stockName += str('({:.0f},{:.0f})%').format(openStrength, lowStrength)
                stockName += '['+str(int(rowData[stock]))+']'
                midArmyCnt += 1
        #中军END
        stockName += '\n---------------'

        #炸板率 -------------------------------
        fail1To2 = 0
        success1To2 = 0
        fail2To3 = 0
        success2To3 = 0
        fail3To4 = 0
        success3To4 = 0
        fail4To5 = 0
        success4To5 = 0
        fail5To6 = 0
        success5To6 = 0
        fail6To7 = 0
        success6To7 = 0
        fail7To8 = 0
        success7To8 = 0
        rushBoardStocks = {
            'fail1To2':'',
            'success1To2':'',
            'fail2To3':'',
            'success2To3':'',
            'fail3To4':'',
            'success3To4':'',
            'fail4To5':'',
            'success4To5':'',
            'fail5To6':'',
            'success5To6':'',
            'fail6To7':'',
            'success6To7':'',
                'fail7To8':'',
            'success7To8':''
        }
        #拿昨天的连板数据统它们在今天的强度和晋级情况
        if i>0:
            #今日掉队BEGIN
            rowData = continuousBoard.iloc[i-1]  #注意是前一天的数据
            removeRowString(rowData)
            rowData = rowData.sort_values(ascending=False)
            startDate = continuousBoard.index.tolist()[i-1]
            endDate = continuousBoard.index.tolist()[i]
            fallBehindCnt = 0
            for stock,boards in rowData.iteritems():
                if '399001' in codes[j] or stock is None or '.' not in stock:
                    continue
                if rowData[stock] < 1:
                    break
                price = get_price(stock, start_date=startDate, end_date=endDate, \
                                     frequency='daily', fields=['open','close','high','high_limit'],\
                                     skip_paused=True, fq='pre')    
                if price.empty or price.shape[0]!=2:
                    continue
                name = get_security_info(stock).display_name
                #昨天连板，今天不在龙头和中军里面那么就是掉队的（有bug，中军过多但是没放进去就成了掉队的）
                if rowData[stock] >= 2 and stock not in midArmyStokcs and fallBehindCnt <= 20:
                    if len(name) == 3:
                        name += '  '
                    if 'ST' in name:
                        name += ' '
                    if '今日掉队' not in stockName:    
                        stockName += '\n>>>>今日掉队<<<<'
                    #计算强度
                    if rowData[stock] == 1 and price.iloc[1]['high'] != price.iloc[1]['high_limit']:
                        continue
                    openStrength = (price.iloc[1]['open']/price.iloc[0]['close']-1)*100
                    closeStrength = (price.iloc[1]['close']/price.iloc[0]['close']-1)*100
                    stockName += '\n'+name+str('({:.0f},{:.0f})%').format(openStrength, closeStrength)
                    stockName += '['+str(int(rowData[stock]))+']'
                    if price.iloc[1]['high'] == price.iloc[1]['high_limit']:
                        stockName += '炸'
                    downRate = (1 - price.iloc[1]['close']/price.iloc[1]['high'])*100
                    if downRate >= 15:
                        stockName += '面'
                    fallBehindCnt += 1

                #今日掉队END
                #炸板统计BEGIN
                #停牌就懒得处理了
                #因为之前统计的是明日的炸板率，所以有炸板情况，但是改成统计今天的炸板率，因为这个循环里面都是今天涨停的，所以有问题
                #这里得拿昨天的数据
                if price.iloc[1]['high'] == price.iloc[1]['high_limit']:
                    if price.iloc[1]['high_limit'] == price.iloc[1]['close']:
                        if 1 == rowData[stock]:
                            success1To2 += 1
                            rushBoardStocks['success1To2'] += str(stock)+','
                        elif 2 == rowData[stock]:
                            success2To3 += 1
                            rushBoardStocks['success2To3'] += str(stock)+','
                        elif 3 == rowData[stock]:
                            success3To4 += 1
                            rushBoardStocks['success3To4'] += str(stock)+','
                        elif 4 == rowData[stock]:
                            success4To5 += 1
                            rushBoardStocks['success4To5'] += str(stock)+','
                        elif 5 == rowData[stock]:
                            success5To6 += 1
                            rushBoardStocks['success5To6'] += str(stock)+','
                        elif 6 == rowData[stock]:
                            success6To7 += 1
                            rushBoardStocks['success6To7'] += str(stock)+','
                        elif 7 == rowData[stock]:
                            success7To8 += 1
                            rushBoardStocks['success7To8'] += str(stock)+','
                    else:
                        if 1 == rowData[stock]:
                            fail1To2 += 1
                            rushBoardStocks['fail1To2'] += str(stock)+','
                        elif 2 == rowData[stock]:
                            fail2To3 += 1
                            rushBoardStocks['fail2To3'] += str(stock)+','
                        elif 3 == rowData[stock]:
                            fail3To4 += 1
                            rushBoardStocks['fail3To4'] += str(stock)+','
                        elif 4 == rowData[stock]:
                            fail4To5 += 1
                            rushBoardStocks['fail4To5'] += str(stock)+','
                        elif 5 == rowData[stock]:
                            fail5To6 += 1
                            rushBoardStocks['fail5To6'] += str(stock)+','
                        elif 6 == rowData[stock]:
                            fail6To7 += 1
                            rushBoardStocks['fail6To7'] += str(stock)+','
                        elif 7 == rowData[stock]:
                            fail7To8 += 1
                            rushBoardStocks['fail7To8'] += str(stock)+','
                #炸板统计END
        #面霸统计，这里需要特别注意的是要拿前天和昨天的连板股来统计，前天的连板股，昨天跌一天或者炸板，今天再跌一天
        #昨天的连板今天炸板跌，或者直接跌2种情况
        #计算都是用这三天的数据来计算
            #昨天连板个股
            rowData = continuousBoard.iloc[i-1]
            removeRowString(rowData)
            rowData = rowData.sort_values(ascending=False)
            for stock,boards in rowData.iteritems():
                if rowData[stock] < minMidCont: 
                    break
                noodleKings.append(stock)  #当日所有连板个股都加入面霸统计
            #前天连板个股
            rowData = continuousBoard.iloc[i-2]
            removeRowString(rowData)
            rowData = rowData.sort_values(ascending=False)
            for stock,boards in rowData.iteritems():
                if rowData[stock] < minMidCont: 
                    break
                noodleKings.append(stock)  #当日所有连板个股都加入面霸统计
            startDate = continuousBoard.index.tolist()[i-2]
            endDate = continuousBoard.index.tolist()[i]
            if len(noodleKings) > 0:
                for item in noodleKings:
                    #拿到最新2天的数据，检查最近2天是否有炸板，有炸板就从炸板的涨停价开始算，没有就用第三天的收盘价算
                    noodlePrice = get_price(item, start_date=startDate, end_date=endDate, \
                            frequency='daily', fields=['close','high','high_limit'],\
                            skip_paused=True, fq='pre')    
                    if noodlePrice.shape[0] == 3:
                        #默认从T-2收盘价开始算
                        downStart = noodlePrice.iloc[0]['close']
                        #如果炸板，那么从涨停价开始算
                        if noodlePrice.iloc[1]['high'] == noodlePrice.iloc[1]['high_limit'] \
                            and noodlePrice.iloc[1]['close'] != noodlePrice.iloc[1]['high_limit']:
                            #T-1天炸板，那么从
                            downStart = noodlePrice.iloc[1]['high']
                        if noodlePrice.iloc[2]['high'] == noodlePrice.iloc[2]['high_limit'] \
                            and noodlePrice.iloc[2]['close'] != noodlePrice.iloc[2]['high_limit']:
                            downStart = noodlePrice.iloc[2]['high']
                        downRate = (1 - noodlePrice.iloc[2]['close']/downStart)*100
                        if downRate >= 15:
                            name = get_security_info(item).display_name
                            noodleKingCnt += 1
        noodleKings = []  #清空，以便统计下一个交易日
        explodeRate = ''
        if fail4To5+success4To5+fail3To4+success3To4+fail2To3+success2To3>0:
            stockName += '\n>>>>梯队晋级<<<<'
        total7To8 = fail7To8+success7To8
        if (total7To8)>0:
            explodeRate = '\n7进8={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail7To8, success7To8, success7To8/total7To8*100)
            stockName += explodeRate
        total6To7 = fail6To7+success6To7
        if (total6To7)>0:
            explodeRate = '\n6进7={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail6To7, success6To7, success6To7/total6To7*100)
            stockName += explodeRate
        total5To6 = fail5To6+success5To6
        if (total5To6)>0:
            explodeRate = '\n5进6={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail5To6, success5To6, success5To6/total5To6*100)
            stockName += explodeRate
        total4To5 = fail4To5+success4To5
        if (total4To5)>0:
            explodeRate = '\n4进5={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail4To5, success4To5, success4To5/total4To5*100)
            stockName += explodeRate
        total3To4 = fail3To4+success3To4
        if (total3To4)>0:
            explodeRate = '\n3进4={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail3To4, success3To4, success3To4/total3To4*100)
            stockName += explodeRate   
        total2To3 = fail2To3+success2To3
        if (total2To3)>0:
            explodeRate = '\n2进3={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail2To3, success2To3, success2To3/total2To3*100)
            stockName += explodeRate
        total1To2 = fail1To2+success1To2
        if (total1To2)>0:
            explodeRate = '\n1进2={:.0f}败/{:.0f}成{:.0f}%'\
            .format(fail1To2, success1To2, success1To2/total1To2*100)
            stockName += explodeRate
        tsDay = str(endDate)
        tsDay = tsDay[0:4]+tsDay[5:7]+tsDay[8:10]
        allPriceData = pro.daily(trade_date = tsDay)
        downLimitData = allPriceData[allPriceData.pct_chg<=-9.9] #当天跌停数据
        upLimitData = allPriceData[allPriceData.pct_chg>=9.9] #当天涨停数据
        if upLimitData.shape[0]>0:
            stockName += '\n----涨停{:.0f}个----'.format(upLimitData.shape[0])
        if downLimitData.shape[0]>0:
            stockName += '\n----跌停{:.0f}个----'.format(downLimitData.shape[0])
        if noodleKingCnt>0:
            stockName += '\n----面霸{:.0f}个----'.format(noodleKingCnt) 
        rowData = continuousBoard.iloc[i]
        stockName += '\n##############'
        stockName += '\n<<<<<<仓  位>>>>>>\n'
        stockName += '['+rowData['marketRate']+']' + '【'+rowData['position']+'】'
        #股票池是供明天打的
        '''stockName += '\n<<<<<股票池>>>>>'
        stockPool = eval(continuousBoard.iloc[i]['stockPool'])
        cnt = 0
        for stock in stockPool:
            if len(stock) < 5:
                continue
            name = '\n' + get_security_info(stock).display_name
            if len(name) == 3:
                name += '   '
            if 'ST' in name:
                name += ' '
            stockName += name 
            cnt += 1
            if cnt > 4:
                break'''
        axPeriod.annotate(stockName, xy=(i, contLimit), \
                     xytext=(xTextPos, yTextPos), xycoords='data',\
                    arrowprops=dict(facecolor='#4DFFFF', shrink=0.01))
        axPeriod.text(i-0.05, contLimit-0.03, int(contLimit), fontsize=16, color='black');
        noodleKingCnt = 0
    picName = "./output/九阳真经.png"
    plt.savefig(picName) # save as png
    plt.show()
    print('制作完毕!')



isTest = False  
#先绘制无断板图后绘制支持断板的高度图
calcDataAndDraw(False)
if not isTest:
    sendEmail('【连板版本】')
calcDataAndDraw(True)
if not isTest:
    sendEmail('【断板版本】')
            
            
            
            
            