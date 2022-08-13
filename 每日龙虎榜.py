import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.pylab as plb
from pylab import mpl
import math
import time
import talib as tl
from datetime import datetime
import jqdata
import mpl_finance as mpf
import matplotlib.image as mpimg
import tushare as ts
import warnings

#龙虎榜日期
date = '2019-10-17'

#过滤警告信息
warnings.filterwarnings("ignore")
#----------------初始化tushare-----------
ts.set_token('d36d566f61ff364b5b6824484426752e1bbbe092dfaaec2d9c2cd996')
pro = ts.pro_api()

#取得2个营业部的关联数
def getRelateCount(relation, depart1, depart2):
    #营业部在表中的位置[depart1,depart2]和[depart2,depart1]
    haveRelation1 = relation[relation.营业部关联表==depart1].shape[0]>0 and \
                    depart2 in relation.columns
    haveRelation2 = relation[relation.营业部关联表==depart2].shape[0]>0 and \
                    depart1 in relation.columns
    if (not haveRelation1) and (not haveRelation2):
        return 0
    count1 = 0
    count2 = 0
    if haveRelation1:
        rowIndex = relation[relation.营业部关联表 == depart1].index.tolist()[0]
        colIndex = list(relation.columns).index(depart2)
        count1 = relation.iloc[rowIndex, colIndex]
    if haveRelation2:
        rowIndex = relation[relation.营业部关联表 == depart2].index.tolist()[0]
        colIndex = list(relation.columns).index(depart1)
        count2 = relation.iloc[rowIndex, colIndex]
    if count1 > 0:
        return count1
    elif count2 > 0:
        return count2
    else:
        return 0
#取得固定20长度的字符串，用空格拼接
def getFixedLenDepart(depart):
    if len(depart)<11:
        return depart+' '*10
    elif len(depart)<15:
        return depart+' '*(15-len(depart))
    else:
        return depart
#优化营业部信息
def parseDepartName(value):
    if value != value:
        return ''
    item = value
    item = item.replace('股份有限公司', '')
    item = item.replace('有限责任公司', '')
    item = item.replace('有限公司', '')
    item = item.replace('东方财富证券', '东财')
    item = item.replace('证券营业部', '')
    item = item.replace('营业部', '')
    return item    
#取得营业部的关联数
def getDepartRlat(relation, buyDeparts, sellDeparts):
    for index,value in enumerate(buyDeparts):
        if ('机构' in value) or ('深股通' in value):
            buyDeparts[index] = '公墓'
        else: buyDeparts[index] = parseDepartName(value)
    for index,value in enumerate(sellDeparts):
        if ('机构' in value) or ('深股通' in value) or ('沪股通' in value):
            buyDeparts[index] = '公墓'
        else: sellDeparts[index] = parseDepartName(value)
    
    #这里不能将买卖的营业部分边，否则同一边的关联营业部就无法统计到关联数
    departs = set(buyDeparts+sellDeparts)
    departs = list(set(departs))
    rlat = pd.DataFrame({'营业部关联表': departs})
    for item in departs:
        if item not in rlat.columns:
            rlat[item] = [0]*len(departs)
    #统计每个股关联的营业部数
    for depart1 in departs:
        for depart2 in departs:
            raltCnt = getRelateCount(relation, depart1, depart2)
            if  raltCnt> 0:
#                 print('%s -> %s' % (depart1, depart2))
                depart1Index = \
                    rlat[rlat.营业部关联表 == depart1].index.tolist()[0]
                rlat.loc[depart1Index, depart2]  = raltCnt
    return rlat


#无用的abnormal_code 106005 106006 106007 106012；都是连续3日的数据
def isUselessAbnormalCode(value):
    if value == '106005' or value == '106006' or value == '106007' or value == '106012':
        return True
    else:
        return False
#过滤连续3日类型的上榜数据
def parseUslAbnormalData(data):
    temp = data
    abmCodes = set(temp['abnormal_code'].tolist())
    theRightCode = 0
    goodAbmCode = '106001 106002 106003 106004'
    for item in list(abmCodes):
        if str(item) in goodAbmCode:
            theRightCode = item
            break
    temp = temp[temp.abnormal_code == theRightCode]
#     print('parseUslAbnormalData %s ' % temp)
    return temp

#去除证券信息
def removeSecurityName(value):
    if '证券' in value:
        value = value[value.index('证券')+2 : len(value)]
    return value


print('\033[1;31m -------------开始制作-------------')
billboard = get_billboard_list(stock_list=None, start_date=date, end_date=date)
#营业部关联表
departRelation = pd.read_csv('./../data/model/optimizedDepartRelation.csv', index_col=0, header=0)
departGroup = pd.read_csv('./../data/model/FullDepartGroup.csv', index_col=0, header=0)
codesInBB = list(set(billboard['code']))#当天所有上榜个股代码
# codesInBB = codesInBB[:10]
rlatCount = pd.DataFrame({'code':[0]*len(codesInBB)})
rlatCount['code'] = codesInBB
rlatCount['count'] = [0]*rlatCount.shape[0]
rlatCount.set_index(['code'], inplace=True)
for code in codesInBB:
    #当天代码为code的股票所有龙虎榜数据
    stockDayBB = billboard[billboard.code == code]
    stockDayBB = parseUslAbnormalData(stockDayBB)
    #忘了为何要删除相同营业部，但是这里有问题，如果营业部做T就要被删掉，暂时注释
    #stockDayBB = stockDayBB.drop_duplicates(subset=['sales_depart_name'],keep='first')
    #当天该股所有上榜营业部
    departs = stockDayBB['sales_depart_name'].tolist()
    #departs = list(set(departs))
    #优化营业部信息
    for index,value in enumerate(departs):
        departs[index] = parseDepartName(value)
    #有关联的营业部放在这，然后用set去重后就是关联的营业部数
    departHaveRlat = []    
    #统计每个股关联的营业部数
    '''
    #这个是关联数，其实用所属分组数更好，比如说10个温州派或者高相关的但是关联数并没有10个
    for depart1 in departs:
        for depart2 in departs:
            if getRelateCount(departRelation, depart1, depart2) > 0:
                departHaveRlat.append(depart1)
                departHaveRlat.append(depart2)
    '''
    count = 0
    for depart in departs:
        group = departGroup[departGroup == depart];
        group = group.dropna(axis=1, how='all')
        group = group.columns.tolist()
        for item in group:
            if '温州' in item or '浙江' in item:
                count += 1
                break
    #rlatCount.loc[code, 'count'] = len(set(departHaveRlat))
    rlatCount.loc[code, 'count'] = count
#     print('%s的关联营业部有：%s' % (code, set(departHaveRlat)))
                
#个股根据关联数降序排序
rlatCount = rlatCount.sort_values(by="count" , ascending=False)  
print('\n\n')
print('*'*50)
print('\033[31m             %s关联数大于5的个股 \033[0m' % date)
i = 1
for index, row in rlatCount.iterrows():
    if row['count'] < 5:
        break
    stockInfo = get_security_info(index)
    try:
        print('%-2d %4s %d  \033[0m' % (i, stockInfo.display_name, row['count']))
        i += 1
    except:
        continue
print('*'*50)
print('\n\n')


#根据关联数从大到小逐一打印报表
for index, row in rlatCount.iterrows():
    #if row['count'] < 5:
    #    return
    #index这里是code
    #当天代码为index的股票所有龙虎榜数据，暂时剔除连续3日的数据
    stockDayBB = billboard[(billboard.code == index)]
    stockDayBB = parseUslAbnormalData(stockDayBB)
    #忘了为何要删除相同营业部，但是这里有问题，如果营业部做T就要被删掉，暂时注释
    #tockDayBB = stockDayBB.drop_duplicates(subset=['sales_depart_name'],keep='first')
    buy = stockDayBB[stockDayBB.direction == 'BUY']
    sell = stockDayBB[stockDayBB.direction == 'SELL']
    try:
        summary = stockDayBB[stockDayBB.direction == 'ALL'].iloc[0]
    except:
        continue
    buy = buy.sort_values(by='rank')
    sell = sell.sort_values(by='rank')
    stockInfo = get_security_info(summary['code'])
    #------------------绘制表头-------------------------
    print('>'*60)
    try:
        print('\033[31m \n %s \033[0m 明细：%s '% \
          (stockInfo.display_name, summary['abnormal_name']))
    except:
        continue
    
    #-----------------绘制K线-----------------------
    plt.close()
    
    # 股票行情数据
    code = summary['code']
    if 'XSHE' in code:
        code = code.replace('XSHE', 'SZ')
    else:
        code = code.replace('XSHG', 'SH')
    df = pro.daily(ts_code=code, start_date='20181101', end_date=date.replace('-', ''))
    df = df.iloc[::-1]   #按行倒置顺序
    
    # 计算均线
    df['ma5'] = pd.Series(tl.MA(df['close'].values,5),index=df.index.values)
    df['ma10'] = pd.Series(tl.MA(df['close'].values,10),index=df.index.values)
    df['ma20'] = pd.Series(tl.MA(df['close'].values,20),index=df.index.values)
    df['ma60'] = pd.Series(tl.MA(df['close'].values,60),index=df.index.values)
    #df['ma120'] = pd.Series(tl.MA(df['close'].values,120),index=df.index.values)
    #df['ma250'] = pd.Series(tl.MA(df['close'].values,250),index=df.index.values)

    # 截取最近30天的数据
    klineCnt = 30
    if df.shape[0] < klineCnt:
        klineCnt = df.shape[0]
    df = df.iloc[-klineCnt:]
    t = range(klineCnt)
    df['t'] = pd.Series(t,index=df.index)
    df = df.set_index('t')

    # 准备画图
    plt.close()
    fig = plt.figure(figsize=(10, 4), frameon=False)

    # 绘制K线 & 绘制均线
    ax1 = plt.subplot2grid((6,1), (0,0), rowspan=3, colspan=1)  
    ax1.set_xlim(0,30)
    ax1.set_axis_off()
    ax1.xaxis.set_major_locator(plt.NullLocator())
    ax1.yaxis.set_major_locator(plt.NullLocator())

    o = list(df['open'].values)
    h = list(df['high'].values)
    l = list(df['low'].values)
    c = list(df['close'].values)
    quotes = zip(t, o, h, l, c)
    mpf.candlestick_ohlc(ax1,quotes, width=0.5, colorup='r', colordown='g')
    df[['ma5', 'ma10', 'ma20', 'ma60']].plot(ax=ax1, legend=False)

    # 绘制成交量柱线
    ax3 = plt.subplot2grid((6,1), (3,0), rowspan=1, colspan=1, sharex=ax1) 
    ax3.set_xlim(0,30)
    ax3.set_axis_off()
    ax3.xaxis.set_major_locator(plt.NullLocator())
    ax3.yaxis.set_major_locator(plt.NullLocator())

    v = list(df['vol'].values)
    barlist = ax3.bar(t,v, width=0.5)
    for i in t:
        if o[i]<c[i]:
            barlist[i].set_color('r')
        else:
            barlist[i].set_color('g')
    plt.show()
    
    #---------------------绘制明细----------------------
    print('\n 成交明细 营业部关联个数：\033[31m %s \033[0m  涨幅：' % row['count'], end='')
    pct_chg = df.iloc[-1]['pct_chg']
    if pct_chg > 0 :
        print('\033[31m %.2f%%\n \033[0m' %  pct_chg)
    else:
        print('\033[32m %.2f%% \033[0m' %  pct_chg)
    totalValue = summary['total_value']/10000
    print('\033[30m 成交额：%d  合计买入：\033[0m' % totalValue, end='')
    buyValue = summary['buy_value']/10000
    print('\033[31m %d ' %  buyValue, end='')
    print('\033[30m 万元   合计卖出：', end='')
    sellValue = summary['sell_value']/10000
    print('\033[32m %d' % sellValue, end='')
    print('\033[30m 万元   净额：', end='')
    netValue = summary['net_value']/10000
    if netValue>0 :
        print('\033[31m %d \033[0m' %  netValue, end='')
    else:
        print('\033[32m %d \033[0m' %  netValue, end='')
    print('\033[30m 万元 \033[0m')
    
    #----------------绘制营业部---------------------
    print('\033[30m \n买入金额最大的前5名营业部       \t 买入额/万 \t 卖出额/万 \t 净额 \033[0m', end='')
    print('\033[31m %d万元 \033[0m' %  buyValue)
    print('-'*80)
    for index, row in buy.iterrows():
        depart = parseDepartName(row['sales_depart_name'])
        group = departGroup[departGroup == depart];
        group = group.dropna(axis=1, how='all')
        group = group.columns.tolist()
        print('-'*80)
        print('\033[30m %-25s \033[0m' %  depart, end='')
        buyValue = row['buy_value']/10000
        buyValue = buyValue if buyValue == buyValue else 0
        print('\033[31m %-15d \033[0m' %  buyValue, end='')
        sellValue = row['sell_value']/10000
        sellValue = sellValue if sellValue == sellValue else 0
        print('\033[32m %-15d \033[0m' %  sellValue, end='')
        netValue = row['net_value']/10000
        netValue = netValue if not math.isnan(netValue) else 0
        print('\033[31m %-10d  \033[0m' %  netValue)
        if len(group)>0:
            print('\033[34m %s \t \033[0m' % group)    
    print('\n')
    print('~'*60)
    print('\n')
    print('\033[30m 卖出金额最大的前5名营业部       \t 买入额/万 \t 卖出额/万 \t 净额 \033[0m', end='')
    netValue = summary['sell_value']/10000
    print('\033[32m %d万元 \033[0m  ' %  netValue)
    print('-'*80)
    for index, row in sell.iterrows():
        depart = parseDepartName(row['sales_depart_name'])
        group = departGroup[departGroup == depart];
        group = group.dropna(axis=1, how='all')
        group = group.columns.tolist()
        print('-'*80)
        print('\033[30m %-25s \033[0m' %  depart, end='')
        buyValue = row['buy_value']/10000
        buyValue = buyValue if buyValue == buyValue else 0
        print('\033[31m %-15d \033[0m' %  buyValue, end='')
        sellValue = row['sell_value']/10000
        sellValue = sellValue if sellValue == sellValue else 0
        print('\033[32m %-15d \033[0m' %  sellValue, end='')
        netValue = row['net_value']/10000
        netValue = netValue if not math.isnan(netValue) else 0
        print('\033[32m %-10d  \033[0m' %  netValue)
        if len(group)>0:
            print('\033[34m %s \t \033[0m' % group)    
    print('~'*60)
    
    #-------------绘制营业部关系图--------------------------
    plt.close()
    plt.figure(figsize=(12, 4))  #设置画布大小
    mpl.rcParams['font.sans-serif'] = ['SimHei'] #解决绘图中文显示问题
    G=nx.Graph()
    relation = getDepartRlat(departRelation, buy['sales_depart_name'].tolist(),\
                             sell['sales_depart_name'].tolist())
    relation.set_index(['营业部关联表'], inplace=True)
    #第一步：生成所有营业部节点
    relation = relation[relation>0]
    #因为营业部列表不是索引，所以在删除行的时候导致一行都删不掉，营业部那列是有值的，改成索引就没问题了
    relation = relation.dropna(axis=0, how='all')  
    relation = relation.dropna(axis=1, how='all') 
    nodes = relation.index.tolist() + relation.columns.tolist();
    #去掉证券名称，营业部名称最简化
    for index,value in enumerate(nodes):
        nodes[index] = removeSecurityName(value)
    G.add_nodes_from(nodes)
    for rowIndex in relation.index:
        for colName in relation.columns:
            if not math.isnan(relation.loc[rowIndex, colName]):
                rowDep = removeSecurityName(rowIndex)
                G.add_edge(rowDep, removeSecurityName(colName), \
                           weight=relation.loc[rowIndex, colName])

#     print('%s 的边数为%s，详细数据为：%s' % (summary['code'], len(G.edges()), G.edges()))
    if len(G.edges()) == 0:
        continue
    #按权重划分为重权值得边和轻权值的边
    largeEdges=[(u,v) for (u,v,d) in G.edges(data=True) if d['weight'] >20]
    midEdges=[(u,v) for (u,v,d) in G.edges(data=True) if d['weight'] >10]
    smallEdges=[(u,v) for (u,v,d) in G.edges(data=True) if d['weight'] <=10]
    #节点位置
    pos=nx.shell_layout(G) # positions for all nodes
    #首先画出节点位置
    nx.draw_networkx_nodes(G,pos,node_size=1, node_color='#FF000000', node_shape='_')
    #画边
    nx.draw_networkx_edges(G,pos,edgelist=smallEdges, width=3, edge_color='#ff7575')
    nx.draw_networkx_edges(G,pos,edgelist=midEdges, width=6, edge_color='#ff7575')
    nx.draw_networkx_edges(G,pos,edgelist=largeEdges, width=10, edge_color='#ff7575', alpha=0.8)
    #画标签
    nx.draw_networkx_labels(G,pos,font_size=12)

    plt.title(stockInfo.display_name+'营业部关系图')
    plt.axis('off')
    #plt.savefig("weighted_graph.png") # save as png
    plt.show()
    