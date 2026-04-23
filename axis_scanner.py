#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time, requests, smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta

WECOM = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=0d944f97-915b-4fa0-b32b-a6f3152e3a33'
TEL_TOKEN = '8096096458:AAEuB-aLBObX2HrqfZ_SgUJfCRgeAmN4zQ8'
TEL_CID = '8690077184'
EM_FROM = 'zmxfll@163.com'
EM_PWD = 'LQvNtdQL3KfL36Cx'
EM_TO = 'henryford198610@gmail.com'
EM_CC = 'zmxfll@163.com'
QQ = '45473891'
QK = 'b87611f2a6132047d0c4b1f8e4e2e3f5'
BINANCE = ['https://fapi.binance.com', 'https://fapi-gcp.binance.com', 'https://fapi1.binance.com']
PUSHED = {}

def push_wecom(msg):
    try:
        r = requests.post(WECOM, json={'msgtype':'text','text':{'content':msg}}, timeout=10)
        return r.status_code == 200 and r.json().get('errcode') == 0
    except: return False

def push_all(msg, subj='轴心中枢信号'):
    push_wecom(msg)
    try: requests.post(f'https://api.telegram.org/bot{TEL_TOKEN}/sendMessage', data={'chat_id':TEL_CID,'text':msg}, timeout=10)
    except: pass
    try:
        em = MIMEText(msg, 'plain', 'utf-8')
        em['Subject'] = Header(subj, 'utf-8')
        em['From'] = EM_FROM
        em['To'] = EM_TO
        if EM_CC: em['Cc'] = EM_CC
        s = smtplib.SMTP_SSL('smtp.163.com', 465)
        s.login(EM_FROM, EM_PWD)
        s.sendmail(EM_FROM, [EM_TO] + ([EM_CC] if EM_CC else []), em.as_string())
        s.quit()
    except: pass
    try: requests.post(f'https://qmsg.zendee.cn/send/{QK}', data={'msg':msg,'qq':QQ}, timeout=10)
    except: pass

def req_binance(ep, params=None, timeout=10):
    for u in BINANCE:
        try:
            r = requests.get(f'{u}{ep}', params=params, timeout=timeout)
            if r.status_code == 200: return r
        except: continue
    return None

def fetch_tickers():
    r = req_binance('/fapi/v1/ticker/24hr', timeout=10)
    if r is not None:
        data = r.json()
        for d in data: d['data_source'] = 'binance'
        print(f'[数据源] 币安成功，获取 {len(data)} 个币种')
        return data
    print('[数据源] 币安全部失败')
    return []

def fetch_klines(sym, interval='1h', limit=60):
    r = req_binance(f'/fapi/v1/klines', params={'symbol':sym,'interval':interval,'limit':limit}, timeout=5)
    if r is None: return None
    d = r.json()
    return {'open':[float(x[1]) for x in d],'high':[float(x[2]) for x in d],'low':[float(x[3]) for x in d],'close':[float(x[4]) for x in d],'volume':[float(x[5]) for x in d]}

def sma(v, p):
    return sum(v[-p:])/p if len(v)>=p else v[-1]

def rsi(c, p=14):
    if len(c)<p+1: return 50.0
    g,l=[],[]
    for i in range(1,len(c)):
        d=c[i]-c[i-1]
        g.append(d if d>0 else 0)
        l.append(-d if d<0 else 0)
    ag=sum(g[-p:])/p
    al=sum(l[-p:])/p
    return 100.0 if al==0 else 100-(100/(1+ag/al))

def bot_div(k):
    c=k['close']
    return len(c)>=30 and min(c[-10:])<min(c[-30:-10])

def top_div(k):
    c=k['close']
    return len(c)>=30 and max(c[-10:])>max(c[-30:-10])

def buy_pt(k):
    l,c=k['low'],k['close']
    return len(l)>=5 and l[-3]<l[-2] and l[-3]<l[-4] and c[-1]>c[-2]

def sell_pt(k):
    h,c=k['high'],k['close']
    return len(h)>=5 and h[-3]>h[-2] and h[-3]>h[-4] and c[-1]<c[-2]

def sharp(k, t):
    m7=sma(k['close'],7)
    return t['lastPrice']<m7 and t.get('vol_ratio',1)>=3

def score(k, t, d):
    if t.get('data_source')!='binance': return 0
    s=0
    c,v=k['close'],k['volume']
    m7=sma(c,7)
    m7p=sma(c[:-1],7) if len(c)>7 else m7
    vr=v[-1]/(sum(v[-7:])/7) if len(v)>=7 else 1
    t['vol_ratio']=vr
    rs=rsi(c)
    g=t.get('priceChangePercent',0)

    if d=='long':
        if -6<=g<=6: s+=15
        if vr<0.3 or (1.5<=vr<=3): s+=25
        if bot_div(k) and buy_pt(k): s+=30
        if t['lastPrice']>m7 and m7>m7p: s+=10
        if rs<30: s+=10
    else:
        if g>=20: s+=15
        if vr>=3: s+=25
        elif vr>=1.2: s+=15
        if top_div(k) and sell_pt(k): s+=30
        elif sharp(k,t): s+=30
        if t['lastPrice']<m7 and m7<m7p: s+=10
        if rs>70: s+=10
    return s

def chk_push(sym, d):
    k=f'{sym}_{d}'
    n=datetime.now()
    if k in PUSHED and (n-PUSHED[k]).seconds<86400: return False
    PUSHED[k]=n
    return True

def ps(sym, d, sc, t):
    if not chk_push(sym,d): return
    dc='起爆' if d=='long' else '下杀'
    lv='S' if sc>=80 else 'A' if sc>=60 else 'B'
    msg=f\"\"\"【轴心·{dc}】{lv}级 评分{sc}
标的：{sym}
涨幅：{t['priceChangePercent']:.1f}%
价格：{t['lastPrice']:.6f}
时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\"\"\"
    push_all(msg, f'轴心·{dc} {sym}')

def main_handler(event, context):
    scan()
    return '扫描完成'

def scan():
    print(f'[{datetime.now()}] 开始扫描...')
    tickers = fetch_tickers()
    if not tickers:
        print('获取行情失败')
        return
    for t in tickers[:100]:
        sym = t['symbol']
        if not sym.endswith('USDT'): continue
        if any(x in sym for x in ['UP','DOWN','BULL','BEAR','USDC','USDP','TUSD']): continue
        k = fetch_klines(sym)
        if not k: continue
        tk = {'lastPrice':float(t['lastPrice']),'priceChangePercent':float(t['priceChangePercent']),'quoteVolume':float(t['quoteVolume']),'data_source':t.get('data_source','binance')}
        if tk['quoteVolume']<30000: continue
        ls = score(k, tk, 'long')
        ss = score(k, tk, 'short')
        if ls>=45: ps(sym, 'long', ls, tk)
        if ss>=45: ps(sym, 'short', ss, tk)
    print(f'[{datetime.now()}] 扫描完成')

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        push_all('✅ 轴心中枢 · 测试消息', '轴心测试')
        print('测试推送已发送')
    else:
        scan()
