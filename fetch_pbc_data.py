#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国人民银行公开市场业务数据抓取 & HTML报告生成 & 邮件推送
适用于 GitHub Actions 自动化运行
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime, timedelta
import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# ===== 配置 =====
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

TODAY = datetime.now().strftime('%Y-%m-%d')
TODAY_DT = datetime.now()

# 邮件配置（从环境变量读取）
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.qq.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT') or '587')
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASS = os.environ.get('SMTP_PASS', '')
EMAIL_TO = os.environ.get('EMAIL_TO', '')

def fetch_page(url, timeout=30):
    """获取页面内容"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.encoding = 'utf-8'
        return r.text
    except Exception as e:
        print(f"[ERROR] 获取页面失败: {url} - {e}")
        return None

def parse_number(text):
    """从中文文本中提取数字（亿元）"""
    if not text:
        return 0
    m = re.search(r'([\d,]+\.?\d*)', text.replace(',', ''))
    if m:
        return float(m.group(1).replace(',', ''))
    return 0

# ===== 1. 抓取7天/14天逆回购 =====
def scrape_reverse_repo():
    """抓取7天/14天逆回购数据（近2个月）"""
    print("\n[1/3] 抓取7天/14天逆回购数据...")
    base_url = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475"
    cutoff = (TODAY_DT - timedelta(days=62)).strftime('%Y-%m-%d')
    
    all_records = []
    
    for page in range(1, 4):
        if page == 1:
            url = f"{base_url}/index.html"
        else:
            url = f"{base_url}/17081-{page}.html"
        
        html = fetch_page(url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        
        for link in links:
            title = link.get_text(strip=True)
            match = re.search(r'\[(\d+)\]第(\d+)号', title)
            if not match:
                continue
            
            href = link.get('href', '')
            date_m = re.search(r'(\d{4})(\d{2})(\d{2})', href)
            if not date_m:
                continue
            date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"
            
            if date < cutoff:
                continue
            
            if href.startswith('http'):
                detail_url = href
            else:
                detail_url = f"https://www.pbc.gov.cn{href}"
            
            detail_html = fetch_page(detail_url)
            if not detail_html:
                continue
            
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            text = detail_soup.get_text()
            
            date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
            op_date = date
            if date_match:
                op_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
            
            amount = 0
            term = '7天'
            rate = '1.40%'
            
            content_div = detail_soup.find('div', id='zoom') or detail_soup.find('div', class_='content') or detail_soup
            tables = content_div.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 4:
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        if any('天' in t for t in cell_texts) and any('亿元' in t for t in cell_texts):
                            for t in cell_texts:
                                if '天' in t and re.search(r'\d+', t):
                                    term = t
                                if '亿元' in t:
                                    amount = parse_number(t)
                            break
            
            if amount == 0:
                m = re.search(r'开展了([\d,]+\.?\d*)亿元(\d+)天期逆回购操作', text)
                if m:
                    amount = parse_number(m.group(1))
                    term = f"{m.group(2)}天"
            
            term_days = 7
            if '14' in term:
                term_days = 14
            try:
                op_dt = datetime.strptime(op_date, '%Y-%m-%d')
                maturity_dt = op_dt + timedelta(days=term_days)
                maturity = maturity_dt.strftime('%Y-%m-%d')
            except:
                maturity = ''
            
            all_records.append({
                'date': op_date,
                'term': term,
                'rate': rate,
                'amount': amount,
                'maturity': maturity,
            })
    
    seen = set()
    unique = []
    for r in sorted(all_records, key=lambda x: x['date'], reverse=True):
        key = (r['date'], r['amount'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    print(f"  获取到 {len(unique)} 条7天/14天逆回购记录")
    return unique

# ===== 2. 抓取买断式逆回购 =====
def scrape_bona_fide_repo():
    """抓取买断式逆回购数据（近24个月）"""
    print("\n[2/3] 抓取买断式逆回购数据...")
    base_url = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845"
    cutoff = (TODAY_DT - timedelta(days=730)).strftime('%Y-%m-%d')
    
    all_records = []
    
    for page in range(1, 5):
        if page == 1:
            url = f"{base_url}/index.html"
        else:
            url = f"{base_url}/17081-{page}.html"
        
        html = fetch_page(url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        
        for link in links:
            title = link.get_text(strip=True)
            if '买断式逆回购' not in title and '公开市场业务' not in title:
                continue
            
            href = link.get('href', '')
            date_m = re.search(r'(\d{4})(\d{2})(\d{2})', href)
            if not date_m:
                continue
            date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"
            
            if date < cutoff:
                continue
            
            if href.startswith('http'):
                detail_url = href
            else:
                detail_url = f"https://www.pbc.gov.cn{href}"
            
            detail_html = fetch_page(detail_url)
            if not detail_html:
                continue
            
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            text = detail_soup.get_text()
            
            date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
            op_date = date
            if date_match:
                op_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
            
            amount = 0
            term = ''
            maturity_date = ''
            
            content_div = detail_soup.find('div', id='zoom') or detail_soup.find('div', class_='content') or detail_soup
            tables = content_div.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        for t in cell_texts:
                            if '个月' in t or '天' in t:
                                if re.search(r'\d+', t):
                                    term = t
                            if '亿元' in t and re.search(r'\d+', t):
                                amount = parse_number(t)
            
            if amount == 0:
                m = re.search(r'([\d,]+)\s*亿元', text)
                if m:
                    amount = parse_number(m.group(1))
            
            if not term:
                tm = re.search(r'(\d+个月|\d+天)', text)
                if tm:
                    term = tm.group(1)
            
            mat_m = re.search(r'到期日[期为：]*\s*(\d{4}年\d{1,2}月\d{1,2}日)', text)
            if mat_m:
                ds = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', mat_m.group(1))
                if ds:
                    maturity_date = f"{ds.group(1)}-{ds.group(2).zfill(2)}-{ds.group(3).zfill(2)}"
            
            if not maturity_date and term:
                days_m = re.search(r'(\d+)', term)
                if days_m:
                    days = int(days_m.group(1))
                    if '月' in term:
                        days = days * 30
                    try:
                        op_dt = datetime.strptime(op_date, '%Y-%m-%d')
                        maturity_date = (op_dt + timedelta(days=days)).strftime('%Y-%m-%d')
                    except:
                        pass
            
            all_records.append({
                'date': op_date,
                'term': term or '未知',
                'amount': amount,
                'maturity': maturity_date,
            })
    
    seen = set()
    unique = []
    for r in sorted(all_records, key=lambda x: x['date'], reverse=True):
        key = (r['date'], r['amount'], r['term'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    print(f"  获取到 {len(unique)} 条买断式逆回购记录")
    return unique

# ===== 3. 抓取MLF =====
def scrape_mlf():
    """抓取MLF数据（近24个月）"""
    print("\n[3/3] 抓取MLF数据...")
    base_url = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125437/125446/125873"
    cutoff = (TODAY_DT - timedelta(days=730)).strftime('%Y-%m-%d')
    
    all_records = []
    
    for page in range(1, 5):
        if page == 1:
            url = f"{base_url}/index.html"
        else:
            url = f"{base_url}/17081-{page}.html"
        
        html = fetch_page(url)
        if not html:
            continue
        
        soup = BeautifulSoup(html, 'html.parser')
        links = soup.find_all('a')
        
        for link in links:
            title = link.get_text(strip=True)
            if 'MLF' not in title and '中期借贷便利' not in title and '开展情况' not in title and '招标' not in title:
                continue
            
            href = link.get('href', '')
            date_m = re.search(r'(\d{4})(\d{2})(\d{2})', href)
            if not date_m:
                continue
            date = f"{date_m.group(1)}-{date_m.group(2)}-{date_m.group(3)}"
            
            if date < cutoff:
                continue
            
            if href.startswith('http'):
                detail_url = href
            else:
                detail_url = f"https://www.pbc.gov.cn{href}"
            
            detail_html = fetch_page(detail_url)
            if not detail_html:
                continue
            
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            text = detail_soup.get_text()
            
            date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
            op_date = date
            if date_match:
                op_date = f"{date_match.group(1)}-{date_match.group(2).zfill(2)}-{date_match.group(3).zfill(2)}"
            
            amount = 0
            rate = ''
            term = '1年'
            
            content_div = detail_soup.find('div', id='zoom') or detail_soup.find('div', class_='content') or detail_soup
            tables = content_div.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        cell_texts = [c.get_text(strip=True) for c in cells]
                        for t in cell_texts:
                            if '亿元' in t and re.search(r'\d+', t):
                                val = parse_number(t)
                                if val > amount:
                                    amount = val
                            if '%' in t and re.search(r'\d+\.?\d*%', t):
                                rate = t.strip()
            
            if amount == 0:
                m = re.search(r'([\d,]+)\s*亿元', text)
                if m:
                    amount = parse_number(m.group(1))
            
            if not rate:
                rm = re.search(r'操作利率[为：]*\s*(\d+\.?\d*%)', text)
                if rm:
                    rate = rm.group(1)
                elif '多重价位' in text:
                    rate = '多重价位'
            
            try:
                op_dt = datetime.strptime(op_date, '%Y-%m-%d')
                maturity_date = (op_dt + timedelta(days=365)).strftime('%Y-%m-%d')
            except:
                maturity_date = ''
            
            all_records.append({
                'date': op_date,
                'term': term,
                'rate': rate or '多重价位',
                'amount': amount,
                'maturity': maturity_date,
            })
    
    seen = set()
    unique = []
    for r in sorted(all_records, key=lambda x: x['date'], reverse=True):
        key = (r['date'], r['amount'])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    
    print(f"  获取到 {len(unique)} 条MLF记录")
    return unique

# ===== 计算统计 =====
def calc_stats(records, today_str):
    """计算统计指标"""
    total_issue = sum(r['amount'] for r in records)
    
    matured = 0
    outstanding = 0
    expiring_soon = 0
    
    for r in records:
        mat = r.get('maturity', '')
        if mat:
            if mat < today_str:
                matured += r['amount']
            else:
                outstanding += r['amount']
                try:
                    mat_dt = datetime.strptime(mat, '%Y-%m-%d')
                    diff = (mat_dt - TODAY_DT).days
                    if 0 <= diff <= 14:
                        expiring_soon += r['amount']
                except:
                    pass
        else:
            outstanding += r['amount']
    
    return {
        'total_issue': total_issue,
        'matured': matured,
        'outstanding': outstanding,
        'net': total_issue - matured,
        'expiring_soon': expiring_soon,
    }

def get_status(maturity, today_str):
    """获取状态标签"""
    if not maturity:
        return '存续中', 'badge-success'
    if maturity == today_str:
        return '今日到期', 'badge-danger'
    try:
        mat_dt = datetime.strptime(maturity, '%Y-%m-%d')
        diff = (mat_dt - TODAY_DT).days
        if diff < 0:
            return '已到期', 'badge-danger'
        elif diff <= 14:
            return '即将到期', 'badge-warning'
        else:
            return '存续中', 'badge-success'
    except:
        return '存续中', 'badge-success'

def format_amount(n):
    """格式化金额"""
    if n == 0:
        return '0'
    if n >= 10000:
        return f"{n:,.0f}"
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.1f}"

# ===== 历史数据管理 =====
def load_history(output_dir):
    """加载历史数据"""
    history_path = os.path.join(output_dir, 'history.json')
    if os.path.exists(history_path):
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_history(output_dir, today_data):
    """保存历史数据"""
    history_path = os.path.join(output_dir, 'history.json')
    history = load_history(output_dir)
    history[TODAY] = today_data
    
    # 只保留最近30天的数据
    cutoff = (TODAY_DT - timedelta(days=30)).strftime('%Y-%m-%d')
    history = {k: v for k, v in history.items() if k >= cutoff}
    
    with open(history_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    
    return history

def calc_change(current, previous):
    """计算变化量和变化百分比"""
    if previous == 0:
        return current, 0
    change = current - previous
    pct = (change / previous) * 100
    return change, pct

def generate_change_text(current_stats, history):
    """生成变化描述文字（邮件正文）"""
    yesterday = (TODAY_DT - timedelta(days=1)).strftime('%Y-%m-%d')
    
    repo = current_stats['repo']
    bona = current_stats['bona']
    mlf = current_stats['mlf']
    
    # 邮件标题和头部
    text = f"""📊 市场流动性日报 - {TODAY}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【附件图片说明】
图片展示了今日三项核心指标的汇总数据卡片，
分别为7天逆回购净投放量、买断式逆回购存续量和MLF净投放量。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【一、7天/14天逆回购（近2个月）】
  净投放量：{format_amount(repo['net'])} 亿元
  总投放量：{format_amount(repo['total_issue'])} 亿元
  总到期量：{format_amount(repo['matured'])} 亿元"""

    if yesterday in history:
        prev = history[yesterday]
        change, pct = calc_change(repo['net'], prev.get('repo_net', 0))
        if change > 0:
            text += f"\n  较昨日：增加 {format_amount(abs(change))} 亿元（+{pct:.1f}%）"
        elif change < 0:
            text += f"\n  较昨日：减少 {format_amount(abs(change))} 亿元（{pct:.1f}%）"
        else:
            text += "\n  较昨日：持平"
    
    text += f"""

【二、买断式逆回购（近24个月）】
  当前存续量：{format_amount(bona['outstanding'])} 亿元
  总投放量：{format_amount(bona['total_issue'])} 亿元
  已到期量：{format_amount(bona['matured'])} 亿元"""

    if yesterday in history:
        prev = history[yesterday]
        change, pct = calc_change(bona['outstanding'], prev.get('bona_outstanding', 0))
        if change > 0:
            text += f"\n  较昨日：增加 {format_amount(abs(change))} 亿元（+{pct:.1f}%）"
        elif change < 0:
            text += f"\n  较昨日：减少 {format_amount(abs(change))} 亿元（{pct:.1f}%）"
        else:
            text += "\n  较昨日：持平"

    text += f"""

【三、MLF 中期借贷便利（近24个月）】
  净投放量：{format_amount(mlf['net'])} 亿元
  总投放量：{format_amount(mlf['total_issue'])} 亿元
  总到期量：{format_amount(mlf['matured'])} 亿元"""

    if yesterday in history:
        prev = history[yesterday]
        change, pct = calc_change(mlf['net'], prev.get('mlf_net', 0))
        if change > 0:
            text += f"\n  较昨日：增加 {format_amount(abs(change))} 亿元（+{pct:.1f}%）"
        elif change < 0:
            text += f"\n  较昨日：减少 {format_amount(abs(change))} 亿元（{pct:.1f}%）"
        else:
            text += "\n  较昨日：持平"

    text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 在线查看完整报告（含图表）：
   https://dgguasa6622.github.io/market-liquidity-report/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
数据来源：中国人民银行官网（www.pbc.gov.cn）
本邮件由 GitHub Actions 自动生成，仅供参考。
"""
    return text

# ===== 生成汇总卡片HTML（用于截图） =====
def generate_summary_card_html(repo_stats, bona_stats, mlf_stats):
    """生成汇总卡片HTML（用于截图发送邮件）"""
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 30px;
            width: 900px;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 25px;
            text-align: center;
            border-radius: 15px 15px 0 0;
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .header .date {{ font-size: 16px; opacity: 0.9; }}
        .cards {{
            display: flex;
            gap: 20px;
            padding: 25px;
            background: white;
            border-radius: 0 0 15px 15px;
        }}
        .card {{
            flex: 1;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 12px;
            padding: 25px;
            text-align: center;
            border-left: 4px solid #2a5298;
        }}
        .card h3 {{ color: #1e3c72; font-size: 16px; margin-bottom: 12px; }}
        .card .amount {{ font-size: 36px; font-weight: 700; color: #2a5298; margin: 10px 0; }}
        .card .unit {{ font-size: 13px; color: #666; }}
        .card .detail {{ margin-top: 12px; font-size: 12px; color: #555; line-height: 1.6; }}
        .footer {{
            text-align: center;
            padding: 15px;
            color: white;
            font-size: 12px;
            opacity: 0.8;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>市场流动性日报</h1>
        <div class="date">{TODAY} | 中国人民银行公开市场业务</div>
    </div>
    <div class="cards">
        <div class="card">
            <h3>7天逆回购净投放量</h3>
            <div class="amount">{format_amount(repo_stats['net'])}</div>
            <div class="unit">亿元（近2个月）</div>
            <div class="detail">
                总投放：{format_amount(repo_stats['total_issue'])}亿<br>
                总到期：{format_amount(repo_stats['matured'])}亿
            </div>
        </div>
        <div class="card">
            <h3>买断式逆回购存续量</h3>
            <div class="amount">{format_amount(bona_stats['outstanding'])}</div>
            <div class="unit">亿元（当前存续）</div>
            <div class="detail">
                总投放：{format_amount(bona_stats['total_issue'])}亿<br>
                已到期：{format_amount(bona_stats['matured'])}亿
            </div>
        </div>
        <div class="card">
            <h3>MLF净投放量</h3>
            <div class="amount">{format_amount(mlf_stats['net'])}</div>
            <div class="unit">亿元（近24个月）</div>
            <div class="detail">
                总投放：{format_amount(mlf_stats['total_issue'])}亿<br>
                总到期：{format_amount(mlf_stats['matured'])}亿
            </div>
        </div>
    </div>
    <div class="footer">数据来源：中国人民银行官网 | 自动生成</div>
</body>
</html>'''
    return html

# ===== 发送邮件 =====
def send_email(subject, body, image_path=None):
    """发送邮件（支持多个收件人，用逗号分隔）"""
    if not all([SMTP_USER, SMTP_PASS, EMAIL_TO]):
        print("[WARN] 邮件配置不完整，跳过发送邮件")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        
        # 支持多个收件人（用逗号或分号分隔）
        recipients = [addr.strip() for addr in EMAIL_TO.replace(';', ',').split(',') if addr.strip()]
        msg['To'] = ', '.join(recipients)
        msg['Subject'] = subject
        
        # 添加文字内容
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 添加图片附件
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(f.read())
            encoders.encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                f'attachment; filename= "{os.path.basename(image_path)}"'
            )
            msg.attach(attachment)
        
        # 发送
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        
        print(f"[INFO] 邮件发送成功: {', '.join(recipients)}")
        return True
    except Exception as e:
        print(f"[ERROR] 邮件发送失败: {e}")
        return False

# ===== 图表数据准备 =====
def prepare_chart_data(records):
    """准备图表所需的数据"""
    sorted_records = sorted(records, key=lambda x: x['date'])
    dates = []
    amounts = []
    for r in sorted_records:
        dates.append(r['date'])
        amounts.append(r['amount'])
    return dates, amounts

def prepare_bona_chart_data(records, today_str):
    """准备买断式逆回购图表数据（累计存续量）"""
    sorted_records = sorted(records, key=lambda x: x['date'])
    dates = []
    outstanding = []
    for r in sorted_records:
        dates.append(r['date'])
        cum = 0
        for rec in records:
            if rec['date'] <= r['date']:
                mat = rec.get('maturity', '')
                if not mat or mat > r['date']:
                    cum += rec['amount']
        outstanding.append(cum)
    return dates, outstanding

def prepare_net_chart_data(records, today_str):
    """准备净投放量图表数据"""
    sorted_records = sorted(records, key=lambda x: x['date'])
    dates = []
    net_values = []
    running_total = 0
    for r in sorted_records:
        dates.append(r['date'])
        running_total += r['amount']
        matured = 0
        for rec in records:
            if rec['date'] <= r['date']:
                mat = rec.get('maturity', '')
                if mat and mat <= r['date']:
                    matured += rec['amount']
        net_values.append(running_total - matured)
    return dates, net_values

# ===== 生成HTML =====
def generate_html(repo_records, bona_records, mlf_records):
    """生成HTML报告（含图表）"""
    today_str = TODAY
    
    repo_stats = calc_stats(repo_records, today_str)
    bona_stats = calc_stats(bona_records, today_str)
    mlf_stats = calc_stats(mlf_records, today_str)
    
    repo_dates, repo_amounts = prepare_chart_data(repo_records)
    repo_dates, repo_net = prepare_net_chart_data(repo_records, today_str)
    bona_dates, bona_amounts = prepare_chart_data(bona_records)
    bona_dates, bona_outstanding = prepare_bona_chart_data(bona_records, today_str)
    mlf_dates, mlf_amounts = prepare_chart_data(mlf_records)
    mlf_dates, mlf_net = prepare_net_chart_data(mlf_records, today_str)
    
    repo_rows = ''
    for i, r in enumerate(repo_records, 1):
        status, badge = get_status(r['maturity'], today_str)
        if r['amount'] == 0:
            status, badge = '无操作', 'badge-info'
        highlight = ' class="highlight"' if r['date'] == today_str else ''
        repo_rows += f'''<tr>
            <td>{i}</td>
            <td{highlight}>{r['date']}</td>
            <td>{r['term']}</td>
            <td>{r['rate']}</td>
            <td>{format_amount(r['amount'])}</td>
            <td>{r['maturity']}</td>
            <td><span class="badge {badge}">{status}</span></td>
        </tr>\n'''
    
    bona_rows = ''
    for i, r in enumerate(bona_records, 1):
        status, badge = get_status(r['maturity'], today_str)
        highlight = ' class="highlight"' if r['date'] == today_str else ''
        bona_rows += f'''<tr>
            <td>{i}</td>
            <td{highlight}>{r['date']}</td>
            <td>{r['term']}</td>
            <td>{format_amount(r['amount'])}</td>
            <td>{r['maturity']}</td>
            <td><span class="badge {badge}">{status}</span></td>
        </tr>\n'''
    
    mlf_rows = ''
    for i, r in enumerate(mlf_records, 1):
        status, badge = get_status(r['maturity'], today_str)
        highlight = ' class="highlight"' if r['date'] == today_str else ''
        mlf_rows += f'''<tr>
            <td>{i}</td>
            <td{highlight}>{r['date']}</td>
            <td>{r['term']}</td>
            <td>{r['rate']}</td>
            <td>{format_amount(r['amount'])}</td>
            <td>{r['maturity']}</td>
            <td><span class="badge {badge}">{status}</span></td>
        </tr>\n'''
    
    repo_dates_json = json.dumps(repo_dates, ensure_ascii=False)
    repo_amounts_json = json.dumps(repo_amounts, ensure_ascii=False)
    repo_net_json = json.dumps(repo_net, ensure_ascii=False)
    bona_dates_json = json.dumps(bona_dates, ensure_ascii=False)
    bona_amounts_json = json.dumps(bona_amounts, ensure_ascii=False)
    bona_outstanding_json = json.dumps(bona_outstanding, ensure_ascii=False)
    mlf_dates_json = json.dumps(mlf_dates, ensure_ascii=False)
    mlf_amounts_json = json.dumps(mlf_amounts, ensure_ascii=False)
    mlf_net_json = json.dumps(mlf_net, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>市场流动性统计报告 - {today_str}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; padding: 20px;
        }}
        .container {{
            max-width: 1400px; margin: 0 auto; background: white;
            border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white; padding: 40px; text-align: center;
        }}
        .header h1 {{ font-size: 2.5em; margin-bottom: 10px; font-weight: 700; }}
        .header .subtitle {{ font-size: 1.1em; opacity: 0.9; }}
        .header .date {{ margin-top: 15px; font-size: 0.95em; opacity: 0.8; }}
        .content {{ padding: 40px; }}
        .summary-cards {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 25px; margin-bottom: 40px;
        }}
        .card {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            border-radius: 15px; padding: 30px; text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            border-left: 5px solid #2a5298;
        }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 10px 30px rgba(0,0,0,0.15); }}
        .card h3 {{ color: #1e3c72; font-size: 1.2em; margin-bottom: 15px; }}
        .card .amount {{ font-size: 2.5em; font-weight: 700; color: #2a5298; margin: 10px 0; }}
        .card .unit {{ font-size: 0.9em; color: #666; }}
        .card .detail {{ margin-top: 15px; font-size: 0.9em; color: #555; line-height: 1.6; }}
        .section {{ margin-bottom: 50px; }}
        .section-title {{
            font-size: 1.8em; color: #1e3c72; margin-bottom: 25px; padding-bottom: 15px;
            border-bottom: 3px solid #2a5298; display: flex; align-items: center; gap: 15px;
        }}
        .section-title .icon {{
            width: 40px; height: 40px; background: #2a5298; border-radius: 10px;
            display: flex; align-items: center; justify-content: center; color: white; font-size: 1.2em;
        }}
        .chart-container {{
            width: 100%; height: 400px; margin: 25px 0;
            background: #fafbfc; border-radius: 15px; padding: 15px;
            box-shadow: 0 2px 15px rgba(0,0,0,0.08);
        }}
        .data-table {{
            width: 100%; border-collapse: collapse; margin-top: 20px; background: white;
            border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .data-table th {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white; padding: 15px; text-align: left; font-weight: 600;
        }}
        .data-table td {{ padding: 12px 15px; border-bottom: 1px solid #eee; }}
        .data-table tr:hover {{ background: #f8f9ff; }}
        .data-table tr:nth-child(even) {{ background: #fafbfc; }}
        .data-table tr:nth-child(even):hover {{ background: #f0f2ff; }}
        .badge {{
            display: inline-block; padding: 4px 12px; border-radius: 20px;
            font-size: 0.85em; font-weight: 600;
        }}
        .badge-success {{ background: #d4edda; color: #155724; }}
        .badge-warning {{ background: #fff3cd; color: #856404; }}
        .badge-danger {{ background: #f8d7da; color: #721c24; }}
        .badge-info {{ background: #d1ecf1; color: #0c5460; }}
        .highlight {{
            background: linear-gradient(120deg, #ffeaa7 0%, #ffeaa7 100%);
            background-repeat: no-repeat; background-size: 100% 40%; background-position: 0 88%;
            font-weight: 600;
        }}
        .stats-grid {{
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px; margin: 25px 0;
        }}
        .stat-box {{
            background: #f8f9fa; border-radius: 10px; padding: 20px;
            text-align: center; border: 2px solid #e9ecef;
        }}
        .stat-box .number {{ font-size: 2em; font-weight: 700; color: #2a5298; }}
        .stat-box .label {{ font-size: 0.9em; color: #666; margin-top: 5px; }}
        .footer {{
            background: #1e3c72; color: white; text-align: center; padding: 30px; font-size: 0.9em;
        }}
        .footer a {{ color: #a8d8ff; text-decoration: none; }}
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 1.8em; }}
            .content {{ padding: 20px; }}
            .data-table {{ font-size: 0.85em; }}
            .data-table th, .data-table td {{ padding: 8px 10px; }}
            .chart-container {{ height: 300px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>市场流动性统计报告</h1>
            <div class="subtitle">中国人民银行公开市场业务数据汇总</div>
            <div class="date">统计日期：{today_str} | 数据自动更新</div>
        </div>
        <div class="content">
            <div class="summary-cards">
                <div class="card">
                    <h3>7天逆回购净投放量</h3>
                    <div class="amount">{format_amount(repo_stats['net'])}</div>
                    <div class="unit">亿元（近2个月）</div>
                    <div class="detail">
                        总投放：{format_amount(repo_stats['total_issue'])}亿元<br>
                        总到期：{format_amount(repo_stats['matured'])}亿元<br>
                        操作次数：{len(repo_records)}次
                    </div>
                </div>
                <div class="card">
                    <h3>买断式逆回购存续量</h3>
                    <div class="amount">{format_amount(bona_stats['outstanding'])}</div>
                    <div class="unit">亿元（当前存续）</div>
                    <div class="detail">
                        近24个月总投放：{format_amount(bona_stats['total_issue'])}亿元<br>
                        已到期：{format_amount(bona_stats['matured'])}亿元<br>
                        操作笔数：{len(bona_records)}笔
                    </div>
                </div>
                <div class="card">
                    <h3>MLF净投放量</h3>
                    <div class="amount">{format_amount(mlf_stats['net'])}</div>
                    <div class="unit">亿元（近24个月）</div>
                    <div class="detail">
                        总投放：{format_amount(mlf_stats['total_issue'])}亿元<br>
                        总到期：{format_amount(mlf_stats['matured'])}亿元<br>
                        操作次数：{len(mlf_records)}次
                    </div>
                </div>
            </div>

            <div class="section">
                <h2 class="section-title">
                    <div class="icon">1</div>
                    7天/14天逆回购统计（近2个月）
                </h2>
                <div class="chart-container" id="repoChart"></div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="number">{len(repo_records)}</div><div class="label">操作次数</div></div>
                    <div class="stat-box"><div class="number">{format_amount(repo_stats['total_issue'])}</div><div class="label">总投放量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(repo_stats['matured'])}</div><div class="label">总到期量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(repo_stats['net'])}</div><div class="label">净投放量（亿元）</div></div>
                </div>
                <table class="data-table">
                    <thead><tr><th>序号</th><th>操作日期</th><th>期限</th><th>操作利率</th><th>中标量（亿元）</th><th>到期日期</th><th>状态</th></tr></thead>
                    <tbody>{repo_rows}</tbody>
                </table>
            </div>

            <div class="section">
                <h2 class="section-title">
                    <div class="icon">2</div>
                    公开市场买断式逆回购统计（近24个月）
                </h2>
                <div class="chart-container" id="bonaChart"></div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="number">{len(bona_records)}</div><div class="label">操作笔数</div></div>
                    <div class="stat-box"><div class="number">{format_amount(bona_stats['total_issue'])}</div><div class="label">总投放量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(bona_stats['matured'])}</div><div class="label">已到期量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(bona_stats['outstanding'])}</div><div class="label">当前存续量（亿元）</div></div>
                </div>
                <table class="data-table">
                    <thead><tr><th>序号</th><th>投放日期</th><th>期限</th><th>中标量（亿元）</th><th>到期日期</th><th>状态</th></tr></thead>
                    <tbody>{bona_rows}</tbody>
                </table>
            </div>

            <div class="section">
                <h2 class="section-title">
                    <div class="icon">3</div>
                    中期借贷便利（MLF）统计（近24个月）
                </h2>
                <div class="chart-container" id="mlfChart"></div>
                <div class="stats-grid">
                    <div class="stat-box"><div class="number">{len(mlf_records)}</div><div class="label">操作次数</div></div>
                    <div class="stat-box"><div class="number">{format_amount(mlf_stats['total_issue'])}</div><div class="label">总投放量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(mlf_stats['matured'])}</div><div class="label">已到期量（亿元）</div></div>
                    <div class="stat-box"><div class="number">{format_amount(mlf_stats['net'])}</div><div class="label">净投放量（亿元）</div></div>
                </div>
                <table class="data-table">
                    <thead><tr><th>序号</th><th>操作日期</th><th>期限</th><th>操作利率</th><th>中标量（亿元）</th><th>到期日期</th><th>状态</th></tr></thead>
                    <tbody>{mlf_rows}</tbody>
                </table>
            </div>
        </div>
        <div class="footer">
            <p>数据来源：中国人民银行官网（www.pbc.gov.cn）</p>
            <p>统计时间：{today_str} | 本报告由GitHub Actions自动生成，仅供参考</p>
        </div>
    </div>
    
    <script>
        var repoChart = echarts.init(document.getElementById('repoChart'));
        var repoOption = {{
            title: {{ text: '7天/14天逆回购操作量变化趋势', left: 'center', textStyle: {{ color: '#1e3c72', fontSize: 16 }} }},
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
            legend: {{ data: ['操作量（亿元）', '累计净投放（亿元）'], top: 30 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: 80, containLabel: true }},
            xAxis: {{ type: 'category', data: {repo_dates_json}, axisLabel: {{ rotate: 45, fontSize: 11 }} }},
            yAxis: {{ type: 'value', name: '金额（亿元）', axisLabel: {{ formatter: '{{value}}' }} }},
            series: [
                {{
                    name: '操作量（亿元）',
                    type: 'bar',
                    data: {repo_amounts_json},
                    itemStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: '#4facfe'}}, {{offset: 1, color: '#00f2fe'}}]) }},
                    barWidth: '50%'
                }},
                {{
                    name: '累计净投放（亿元）',
                    type: 'line',
                    data: {repo_net_json},
                    smooth: true,
                    lineStyle: {{ color: '#e74c3c', width: 3 }},
                    itemStyle: {{ color: '#e74c3c' }},
                    areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: 'rgba(231,76,60,0.3)'}}, {{offset: 1, color: 'rgba(231,76,60,0.05)'}}]) }}
                }}
            ]
        }};
        repoChart.setOption(repoOption);
        
        var bonaChart = echarts.init(document.getElementById('bonaChart'));
        var bonaOption = {{
            title: {{ text: '买断式逆回购累计存续量变化趋势', left: 'center', textStyle: {{ color: '#1e3c72', fontSize: 16 }} }},
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
            legend: {{ data: ['单笔操作量（亿元）', '累计存续量（亿元）'], top: 30 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: 80, containLabel: true }},
            xAxis: {{ type: 'category', data: {bona_dates_json}, axisLabel: {{ rotate: 45, fontSize: 10 }} }},
            yAxis: {{ type: 'value', name: '金额（亿元）', axisLabel: {{ formatter: '{{value}}' }} }},
            dataZoom: [{{ type: 'inside', start: 0, end: 100 }}, {{ start: 0, end: 100 }}],
            series: [
                {{
                    name: '单笔操作量（亿元）',
                    type: 'bar',
                    data: {bona_amounts_json},
                    itemStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: '#43e97b'}}, {{offset: 1, color: '#38f9d7'}}]) }},
                    barWidth: '40%'
                }},
                {{
                    name: '累计存续量（亿元）',
                    type: 'line',
                    data: {bona_outstanding_json},
                    smooth: true,
                    lineStyle: {{ color: '#8e44ad', width: 3 }},
                    itemStyle: {{ color: '#8e44ad' }},
                    areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: 'rgba(142,68,173,0.3)'}}, {{offset: 1, color: 'rgba(142,68,173,0.05)'}}]) }}
                }}
            ]
        }};
        bonaChart.setOption(bonaOption);
        
        var mlfChart = echarts.init(document.getElementById('mlfChart'));
        var mlfOption = {{
            title: {{ text: 'MLF净投放量变化趋势', left: 'center', textStyle: {{ color: '#1e3c72', fontSize: 16 }} }},
            tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
            legend: {{ data: ['单次操作量（亿元）', '累计净投放（亿元）'], top: 30 }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', top: 80, containLabel: true }},
            xAxis: {{ type: 'category', data: {mlf_dates_json}, axisLabel: {{ rotate: 45, fontSize: 10 }} }},
            yAxis: {{ type: 'value', name: '金额（亿元）', axisLabel: {{ formatter: '{{value}}' }} }},
            dataZoom: [{{ type: 'inside', start: 0, end: 100 }}, {{ start: 0, end: 100 }}],
            series: [
                {{
                    name: '单次操作量（亿元）',
                    type: 'bar',
                    data: {mlf_amounts_json},
                    itemStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: '#fa709a'}}, {{offset: 1, color: '#fee140'}}]) }},
                    barWidth: '40%'
                }},
                {{
                    name: '累计净投放（亿元）',
                    type: 'line',
                    data: {mlf_net_json},
                    smooth: true,
                    lineStyle: {{ color: '#e67e22', width: 3 }},
                    itemStyle: {{ color: '#e67e22' }},
                    areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{{offset: 0, color: 'rgba(230,126,34,0.3)'}}, {{offset: 1, color: 'rgba(230,126,34,0.05)'}}]) }}
                }}
            ]
        }};
        mlfChart.setOption(mlfOption);
        
        window.addEventListener('resize', function() {{
            repoChart.resize();
            bonaChart.resize();
            mlfChart.resize();
        }});
    </script>
</body>
</html>'''
    return html

# ===== 主函数 =====
def main():
    print(f"=== 市场流动性统计报告生成 ===")
    print(f"统计日期: {TODAY}")
    
    output_dir = os.environ.get('OUTPUT_DIR', 'docs')
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载历史数据
    history = load_history(output_dir)
    
    # 1. 抓取数据
    repo_records = scrape_reverse_repo()
    bona_records = scrape_bona_fide_repo()
    mlf_records = scrape_mlf()
    
    # 2. 计算统计
    repo_stats = calc_stats(repo_records, TODAY)
    bona_stats = calc_stats(bona_records, TODAY)
    mlf_stats = calc_stats(mlf_records, TODAY)
    
    current_stats = {
        'repo': repo_stats,
        'bona': bona_stats,
        'mlf': mlf_stats,
    }
    
    # 3. 保存历史数据
    today_data = {
        'repo_net': repo_stats['net'],
        'bona_outstanding': bona_stats['outstanding'],
        'mlf_net': mlf_stats['net'],
    }
    history = save_history(output_dir, today_data)
    
    # 4. 生成变化描述
    change_text = generate_change_text(current_stats, history)
    print("\n变化描述：")
    print(change_text)
    
    # 5. 生成汇总卡片HTML
    summary_html = generate_summary_card_html(repo_stats, bona_stats, mlf_stats)
    summary_path = os.path.join(output_dir, 'summary.html')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_html)
    
    # 6. 生成完整HTML报告
    print("\n生成HTML报告...")
    html = generate_html(repo_records, bona_records, mlf_records)
    
    output_path = os.path.join(output_dir, 'index.html')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"报告已保存到: {output_path}")
    
    # 7. 保存JSON数据
    data = {
        'date': TODAY,
        'reverse_repo': repo_records,
        'bona_fide_repo': bona_records,
        'mlf': mlf_records,
    }
    data_path = os.path.join(output_dir, 'data.json')
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"原始数据已保存到: {data_path}")
    
    # 8. 生成图片（如果安装了playwright）
    image_path = None
    try:
        from playwright.sync_api import sync_playwright
        print("\n生成报告图片...")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={'width': 900, 'height': 600})
            page.goto(f'file://{os.path.abspath(summary_path)}')
            page.wait_for_timeout(1000)
            image_path = os.path.join(output_dir, 'summary.png')
            page.screenshot(path=image_path, full_page=True)
            browser.close()
        print(f"图片已保存到: {image_path}")
    except ImportError:
        print("[WARN] 未安装 playwright，跳过图片生成")
    except Exception as e:
        print(f"[WARN] 图片生成失败: {e}")
    
    # 9. 发送邮件
    if SMTP_USER and SMTP_PASS and EMAIL_TO:
        print("\n发送邮件通知...")
        subject = f"📊 市场流动性日报 - {TODAY}"
        send_email(subject, change_text, image_path)
    else:
        print("[INFO] 邮件配置不完整，跳过发送邮件")
        print("如需发送邮件，请设置环境变量: SMTP_USER, SMTP_PASS, EMAIL_TO")
    
    print("\n完成！")

if __name__ == '__main__':
    main()
