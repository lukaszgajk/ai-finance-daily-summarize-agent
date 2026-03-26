import os
import urllib.request
import xml.etree.ElementTree as ET
import yfinance as yf
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from crewai import Agent, Task, Crew, Process, LLM

def scrape_article_text(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        article_text = " ".join([p.text for p in paragraphs if len(p.text) > 40])
        
        if len(article_text) > 2000:
            return article_text[:2000] + "... (content shortened)"
        return article_text
    except Exception:
        return "Failed to retrieve full content."

def fetch_full_news_today_list(ticker: str) -> list:
    url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    todays_news_list = []
    
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            if not items: return todays_news_list
            
            today = datetime.now(timezone.utc).date()
            for item in items:
                pub_date_str = item.find('pubDate').text
                if pub_date_str:
                    item_date = parsedate_to_datetime(pub_date_str).date()
                    if item_date == today:
                        title = item.find('title').text
                        link = item.find('link').text
                        full_text = scrape_article_text(link)
                        todays_news_list.append({"title": title, "content": full_text})
            return todays_news_list
    except Exception as e:
        return todays_news_list

def fetch_stock_data(ticker: str):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="ytd")
    if hist.empty: return "N/A", "N/A"
    
    current_price = hist['Close'].iloc[-1]
    start_ytd_price = hist['Close'].iloc[0]
    ytd_percent = ((current_price - start_ytd_price) / start_ytd_price) * 100
    
    return round(current_price, 2), round(ytd_percent, 2)

os.environ["USER_AGENT"] = "MyFinanceAgent/1.0"
llm = LLM(model="ollama/llama3.1", base_url="http://ollama:11434")

portfolio = ["MSFT", "NVDA", "AAPL"]

# ========================================================
# 1. HTML & CSS TEMPLATE SETUP
# ========================================================
todays_date = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M")

html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Stock Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f7f6;
            color: #333;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 5px;
        }}
        .subtitle {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 40px;
            font-size: 1.1em;
        }}
        .card {{
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.05);
            padding: 30px;
            margin-bottom: 30px;
            border-left: 6px solid #2980b9;
        }}
        .card h2 {{
            color: #2980b9;
            margin-top: 0;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
            font-size: 1.8em;
        }}
        .metrics {{
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 1.1em;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metrics span {{
            color: #27ae60;
        }}
        .metrics span.negative {{
            color: #e74c3c;
        }}
        .ai-text {{
            line-height: 1.7;
            font-size: 1.05em;
            color: #444;
        }}
        /* Dodane style dla ładnych wypunktowań */
        .ai-text ul {{
            padding-left: 20px;
        }}
        .ai-text li {{
            margin-bottom: 10px;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            color: #95a5a6;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 Your Daily Stock Report</h1>
        <div class="subtitle">Generated by Artificial Intelligence • {todays_date}</div>
"""

# ========================================================
# 2. MAIN AGENT LOOP
# ========================================================
for ticker_symbol in portfolio:
    print(f"\n🔄 Starting analysis for ticker: {ticker_symbol} ...")
    
    articles_list = fetch_full_news_today_list(ticker_symbol)
    current_price, ytd_percent = fetch_stock_data(ticker_symbol)

    reader_agent = Agent(
        role='News Reader and Summarizer',
        goal='Read individual articles and extract the most critical facts.',
        backstory='You are a fast-reading assistant. You provide short, factual bullet points.',
        allow_delegation=False,
        llm=llm
    )

    chief_analyst = Agent(
        role='Chief Equity Analyst',
        goal='Analyze the notes and output 5 insights.',
        backstory='You are a senior analyst.',
        allow_delegation=False,
        llm=llm
    )

    all_tasks = []
    reading_tasks = []

    if articles_list:
        for article in articles_list:
            task = Task(
                description=f"Read this article:\nTITLE: {article['title']}\nCONTENT: {article['content']}\n\nExtract exactly 2 most important bullet points.",
                expected_output='2 concise bullet points.',
                agent=reader_agent
            )
            all_tasks.append(task)
            reading_tasks.append(task)

    final_task = Task(
        description=f"""
        Using the notes generated by the News Reader, write a DETAILED, 5-point summary in ENGLISH about {ticker_symbol}.
        If there are no notes, state that explicitly.
        Please provide 5 bullet points starting with a hyphen (-).
        """,
        expected_output='A 5-point list.',
        agent=chief_analyst,
        context=reading_tasks
    )
    all_tasks.append(final_task)

    crew = Crew(agents=[reader_agent, chief_analyst], tasks=all_tasks, process=Process.sequential)
    company_result = crew.kickoff()
    
    # --- NOWOŚĆ: CZYSZCZENIE WYJŚCIA PRZEZ PYTHONA ---
    raw_text = company_result.raw
    
    # Szukamy wszystkich linijek, które zaczynają się od myślnika (-), gwiazdki (*) lub liczby (np. 1., 2.)
    # Wyciągamy samą treść punktu ignorując śmieci dookoła.
    znalezione_punkty = re.findall(r'^(?:[-*]|\d+\.)\s*(.+)', raw_text, re.MULTILINE)
    
    if znalezione_punkty:
        # Jeśli Python znalazł punkty, buduje perfekcyjną, czystą listę HTML
        czysty_html_listy = "<ul>\n"
        for punkt in znalezione_punkty:
            czysty_html_listy += f"<li>{punkt}</li>\n"
        czysty_html_listy += "</ul>"
    else:
        # Jeśli z jakiegoś powodu model w ogóle nie użył punktów (np. napisał "Brak wiadomości na dziś")
        czysty_html_listy = f"<p>{raw_text}</p>"

    # Kolorowanie YTD
    ytd_class = "negative" if isinstance(ytd_percent, float) and ytd_percent < 0 else ""
    
    html_content += f"""
        <div class="card">
            <h2>{ticker_symbol}</h2>
            <div class="metrics">
                Price: ${current_price} <br>
                YTD: <span class="{ytd_class}">{ytd_percent}%</span>
            </div>
            <div class="ai-text">{czysty_html_listy}</div>
        </div>
    """

# ========================================================
# 3. FINALIZE AND SAVE HTML FILE
# ========================================================
html_content += """
        <div class="footer">
            Report generated locally by Llama 3.1 & CrewAI.
        </div>
    </div>
</body>
</html>
"""

file_name = "portfolio_report.html"
with open(file_name, "w", encoding="utf-8") as file:
    file.write(html_content)

print(f"\n🎉 SUCCESS! Your generated report is ready in: {file_name}")