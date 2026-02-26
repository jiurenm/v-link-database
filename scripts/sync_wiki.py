"""
从 pjsekai Wiki 抓取乐曲列表与详情。
- 列表页：提取 wiki_id、group、难度。
- 详情页（每首歌点进去）：从 楽曲DATA 提取 作詞/作曲（P主，以作曲为主）、音源 セカイver.（歌手）。
首次全量：python sync_wiki.py --full
后续定时：python sync_wiki.py  只对新增或缺少 P主/歌手的歌曲进详情页抓取。
"""
import requests
from bs4 import BeautifulSoup
import json
import os
import time

def fetch_song_detail(wiki_id):
    """进入歌曲详情页，从 楽曲DATA 抓取 作詞/作曲（P主）和 音源 セカイver.（歌手）。"""
    url = f"https://pjsekai.com/?{wiki_id}"
    out = {"lyricist": None, "composer": None, "sekai_singer": None}
    try:
        resp = requests.get(url, timeout=15)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        for h in soup.find_all(["h3", "h4"]):
            if "楽曲DATA" not in (h.get_text() or ""):
                continue
            t = h.find_next("table")
            if not t:
                continue
            for row in t.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue
                key = cells[0].get_text(strip=True)
                if key == "作詞":
                    out["lyricist"] = cells[1].get_text(strip=True) or None
                elif key == "作曲":
                    out["composer"] = cells[1].get_text(strip=True) or None
                elif key == "音源" and len(cells) >= 3:
                    # 第二列为「セカイver.」时，第三列为歌手
                    if cells[1].get_text(strip=True) == "セカイver.":
                        val = cells[2].get_text(strip=True)
                        out["sekai_singer"] = val if val and val != "-" else None
            break
        return out
    except Exception as e:
        print(f"  ⚠ 详情页抓取失败 {wiki_id}: {e}")
        return out


def update_local_wiki_data(full_fetch=False):
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

        # --- 加载已有 meta，用于增量时保留已有 P主/歌手 ---
        existing_meta = {}
        meta_path = "./data/songs_meta.json"
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    existing_meta = json.load(f)
            except Exception:
                pass

        # --- 确定需要进入详情页抓取的歌曲（增量时只抓「从未抓过详情」或新歌）---
        need_detail = []
        for jp_name, entry in meta_db.items():
            wiki_id = entry.get("wiki_id") or ""
            if not wiki_id:
                continue
            if full_fetch:
                need_detail.append((jp_name, wiki_id))
            else:
                # 增量：仅当本地没有该歌，或该歌从未跑过详情页（detail_fetched；兼容旧数据：已有 composer/sekai_singer 视为已抓过）
                prev = existing_meta.get(jp_name) if isinstance(existing_meta, dict) else None
                already_fetched = prev and (prev.get("detail_fetched") or "composer" in prev or "sekai_singer" in prev)
                if not already_fetched:
                    need_detail.append((jp_name, wiki_id))

        # --- 保留已有条目中的 P主/歌手（增量时未重抓的歌曲）---
        for jp_name, entry in meta_db.items():
            prev = existing_meta.get(jp_name) if isinstance(existing_meta, dict) else None
            if prev:
                entry.setdefault("lyricist", prev.get("lyricist"))
                entry.setdefault("composer", prev.get("composer"))
                entry.setdefault("sekai_singer", prev.get("sekai_singer"))
                entry.setdefault("detail_fetched", prev.get("detail_fetched"))

        # --- 进入详情页抓取 P主、歌手 ---
        total = len(need_detail)
        if total:
            print(f"进入详情页抓取 P主/歌手，共 {total} 首（{'全量' if full_fetch else '增量'}）...")
        for i, (jp_name, wiki_id) in enumerate(need_detail):
            detail = fetch_song_detail(wiki_id)
            meta_db[jp_name]["lyricist"] = detail.get("lyricist")
            meta_db[jp_name]["composer"] = detail.get("composer")
            meta_db[jp_name]["sekai_singer"] = detail.get("sekai_singer")
            meta_db[jp_name]["detail_fetched"] = True
            if (i + 1) % 20 == 0 or i == total - 1:
                print(f"  已处理 {i + 1}/{total} 首")
            time.sleep(0.5)

        # 存入本地文件
        os.makedirs("./data", exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_db, f, ensure_ascii=False, indent=2)

        print(f"✅ 更新成功！已保存 {len(meta_db)} 首歌曲信息。")
        if total:
            print(f"   其中本轮抓取详情 {total} 首（P主/セカイver.）。")

    except Exception as e:
        print(f"❌ 更新失败: {e}")


if __name__ == "__main__":
    import sys
    full_fetch = "--full" in sys.argv
    update_local_wiki_data(full_fetch=full_fetch)