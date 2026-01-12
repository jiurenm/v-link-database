import requests
from bs4 import BeautifulSoup
import json
import os

def update_local_wiki_data():
    url = "https://pjsekai.com/?aad6ee23b0"
    
    # 定义组合映射表
    UNIT_MAP = {
        "0_VS": "Virtual Singer",
        "1_L/n": "Leo/need",
        "2_MMJ": "MORE MORE JUMP！",
        "3_VBS": "Vivid BAD SQUAD",
        "4_WxS": "ワンダーランズ×ショウタイム",
        "5_25": "25時、ナイトコードで。",
        "9_oth": "Other"
    }

    print("正在从 Wiki 抓取数据并提取歌曲 ID...")
    
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        table = soup.find('table', id='sortable_table1')
        if not table:
            print("未能找到数据表格。")
            return

        meta_db = {}
        rows = table.find_all('tr')
        
        for row in rows[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) < 10:
                continue
            
            # --- 1. 提取组合 (Unit) ---
            unit_raw = cols[4].get_text(strip=True)
            unit_name = "Other"
            for key, val in UNIT_MAP.items():
                if key in unit_raw:
                    unit_name = val
                    break
            
            # --- 2. 提取歌名和 Wiki ID ---
            name_col = cols[3]
            jp_name = name_col.get_text(strip=True)
            
            # 提取 href 中的 ID (例如 ?708ecb0c47)
            wiki_id = ""
            a_tag = name_col.find('a')
            if a_tag and 'href' in a_tag.attrs:
                href = a_tag['href']
                if '?' in href:
                    wiki_id = href.split('?')[-1] # 获取 ? 后面的内容
            
            # --- 3. 提取难度数据 ---
            # 考虑 APPEND 难度可能在第 11 列 (cols[10])
            append_diff = cols[10].get_text(strip=True) if len(cols) > 10 else "-"
            
            meta_db[jp_name] = {
                "wiki_id": wiki_id,  # 保存提取到的 ID
                "group": unit_name,
                "difficulty": {
                    "easy": cols[5].get_text(strip=True),
                    "normal": cols[6].get_text(strip=True),
                    "hard": cols[7].get_text(strip=True),
                    "expert": cols[8].get_text(strip=True),
                    "master": cols[9].get_text(strip=True),
                    "append": append_diff
                }
            }

        meta_db["どんな結末がお望みだい？"] = {
            "wiki_id": "de408f6e84",
            "group": "ワンダーランズ×ショウタイム",
            "difficulty": {
                "easy": "8",
                "normal": "12",
                "hard": "17",
                "expert": "24",
                "master": "28",
                "append": "-"
            }
        }

        meta_db["Chu! Future☆Express!"] = {
            "wiki_id": "b2f5bb1f6a",
            "group": "Virtual Singer",
            "difficulty": {
                "easy": "9",
                "normal": "14",
                "hard": "19",
                "expert": "26",
                "master": "30",
                "append": "-"
            }
        }

        meta_db["New Worlds"] = {
            "wiki_id": "New Worlds",
            "group": "Virtual Singer",
            "difficulty": {
                "easy": "7",
                "normal": "12",
                "hard": "17",
                "expert": "23",
                "master": "28",
                "append": "-"
            }
        }
            
        # 存入本地文件
        os.makedirs('./data', exist_ok=True)
        with open('./data/songs_meta.json', 'w', encoding='utf-8') as f:
            json.dump(meta_db, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 更新成功！已保存 {len(meta_db)} 首歌曲信息。")
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")

if __name__ == "__main__":
    update_local_wiki_data()