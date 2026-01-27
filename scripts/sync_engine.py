import requests
import re
import json
import time
import os

from wbi import getWbiKeys, encWbi

# --- 核心映射配置 ---
CHARACTER_DB = {
    "宵崎奏": "25時", "東雲絵名": "25時", "暁山瑞希": "25時", "朝比奈まふゆ": "25時",
    "星乃一歌": "Leo/need", "天馬咲希": "Leo/need", "望月穂波": "Leo/need", "日野森志歩": "Leo/need",
    "花里みのり": "MMJ", "桐谷遥": "MMJ", "桃井愛莉": "MMJ", "日野森雫": "MMJ",
    "小豆沢こはね": "VBS", "白石杏": "VBS", "東雲彰人": "VBS", "青柳冬弥": "VBS",
    "天馬司": "WxS", "凤えむ": "WxS", "草薙寧々": "WxS", "神代類": "WxS",
    "初音ミク": "Virtual Singer", "镜音リン": "Virtual Singer", "镜音レン": "Virtual Singer", 
    "巡音ルカ": "Virtual Singer", "MEIKO": "Virtual Singer", "KAITO": "Virtual Singer"
}

KNOWN_GROUPS = [
    "Vivid BAD SQUAD", "ワンダーランズ×ショウタイム", "25時、ナイトコードで。", 
    "Leo/need", "MORE MORE JUMP！"
]

COMPOSER_BLACKLIST = ["MV", "字幕", "世界计划", "収录", "主题曲", "游戏"]

def extract_brackets(raw_title):
    return re.findall(r'【(.*?)】', raw_title)

class VLinkSyncEngine:
    def __init__(self, mid="13148307", season_id="1547037"):
        self.api_url = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"

        self.img_key, self.sub_key = getWbiKeys()

        self.params = {
            'mid': mid,
            'season_id': season_id,
            'sort_reverse': 'false',
            'page_size': 30,
            'page_num': 1
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.songs_map = {}
        
        # --- 新增：载入本地抓取的 Meta 数据 ---
        self.meta_db = self.load_meta_db()
        self.manual_mapping = self.load_manual_mapping()

    def load_manual_mapping(self):
        path = './data/mapping.json'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def load_meta_db(self):
        """载入由 sync_wiki.py 生成的元数据"""
        path = './data/songs_meta.json'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        print("⚠️ 警告：未找到 ./data/songs_meta.json，将无法匹配难度数据")
        return {}

    def find_meta_info(self, title):
        """在 meta_db 中匹配歌名，尝试直接匹配和归一化匹配"""
        search_title = self.manual_mapping.get(title, title)

        # 1. 直接匹配
        if search_title in self.meta_db:
            return search_title, self.meta_db[search_title]
        
        clean_t = search_title.replace(" ", "").lower()
        for jp_name, info in self.meta_db.items():
            if jp_name.replace(" ", "").lower() == clean_t:
                return jp_name, info
                
        return search_title, None

    def clean_title_and_artist(self, raw_title):
        brackets = extract_brackets(raw_title)
        artist = "Unknown Producer"
        
        for b in brackets:
            if any(x in b for x in COMPOSER_BLACKLIST):
                continue
            if "×" in b or "*" in b:
                artist = b
                break

        title_body = re.sub(r'【.*?】', '', raw_title)
        title_body = re.sub(r'（.*?）|\(.*?\)', '', title_body)
        title_body = re.sub(r'／.*$', '', title_body).strip()

        for group in KNOWN_GROUPS:
            if artist.startswith(group):
                artist = group
                break

        return title_body, artist

    def parse_vocalists(self, raw_title):
        brackets = extract_brackets(raw_title)
        vocal_bracket = None
        
        for b in brackets:
            if "字幕" in b or "MV" in b or "世界计划" in b:
                continue
            if any(v in b for v in CHARACTER_DB):
                vocal_bracket = b
                break

        if not vocal_bracket:
            return ["Virtual Singer"], "Other", "Virtual Singer"

        vocalists = []
        remainder = vocal_bracket
        for group in KNOWN_GROUPS:
            if group in remainder:
                vocalists.append(group)
                remainder = remainder.replace(group, "")

        singers = [v.strip() for v in re.split(r'[×、&/]', remainder) if v.strip()]
        vocalists.extend(singers)

        main_group = next((v for v in vocalists if v in KNOWN_GROUPS), "Other")
        groups_found = [CHARACTER_DB[v] for v in vocalists if v in CHARACTER_DB if CHARACTER_DB[v] != "Virtual Singer"]
        vocal_type = "Sekai" if groups_found else "Virtual Singer"

        return vocalists, main_group, vocal_type

    def run(self):
        total_pages = 1
        current_page = 1
        
        while current_page <= total_pages:
            self.params['page_num'] = current_page
            print(f"📡 正在拉取第 {current_page} 页数据...")
            
            try:
                signed = encWbi(
                    params=self.params,
                    img_key=self.img_key,
                    sub_key=self.sub_key
                )
                resp = requests.get(self.api_url, params=signed, headers=self.headers).json()
                if resp['code'] != 0: 
                    print("⚠️ API 请求失败")
                    break
                
                data = resp['data']
                total_pages = (data['page']['total'] // self.params['page_size']) + 1
                
                for arc in data['archives']:
                    raw_title = arc['title']
                    title, artist = self.clean_title_and_artist(raw_title)
                    
                    # --- 匹配 Meta 数据 ---
                    std_title, meta_info = self.find_meta_info(title)
                    
                    if title not in self.songs_map:
                        vocalists, main_group, vocal_type = self.parse_vocalists(raw_title)
                        v_type_label = '3D' if '3DMV' in raw_title.upper() else '2D'
                        
                        self.songs_map[std_title] = {
                            "id": f"pjsk_{arc['aid']}",
                            "wiki_id": meta_info.get("wiki_id") if meta_info else None, # 注入 Wiki ID
                            "title": std_title,
                            "artist": artist,
                            "is_pjsk": True,
                            "total_views": 0,
                            "cover_url": None,
                            "pjsk_meta": None,
                            "versions": [],
                            "updated_at": arc.get('ctime', 0)
                        }
                        
                        if self.songs_map[std_title]["is_pjsk"]:
                            # 优先使用 Wiki 爬到的 Group 信息
                            final_group = meta_info.get("group") if meta_info else main_group
                            
                            self.songs_map[std_title]["pjsk_meta"] = {
                                "main_group": final_group,
                                "vocalist_type": "Full" if len(set(vocalists)) > 1 else "Unit",
                                "difficulty": meta_info.get("difficulty") if meta_info else None
                            }

                    # 更新播放量和版本
                    v_type_label = '3D' if '3DMV' in raw_title.upper() else '2D'
                    vocalists, _, vocal_type = self.parse_vocalists(raw_title)
                    
                    self.songs_map[std_title]["total_views"] += arc['stat']['view']
                    ctime = arc.get('ctime', 0)
                    self.songs_map[std_title]["versions"].append({
                        "type": v_type_label,
                        "label": f"{v_type_label} MV",
                        "bvid": arc['bvid'],
                        "duration": arc['duration'],
                        "vocalists": vocalists,
                        "vocal_type": vocal_type,
                        "views": arc['stat']['view'],
                        "ctime": ctime
                    })
                    
                    # 更新 updated_at 为所有版本中最新的 ctime
                    max_ctime = max(
                        [v.get('ctime', 0) for v in self.songs_map[std_title]["versions"]],
                        default=0
                    )
                    self.songs_map[std_title]["updated_at"] = max_ctime

                    if v_type_label == '2D':
                        self.songs_map[std_title]["cover_url"] = arc['pic']
                    elif v_type_label == '3D' and not self.songs_map[std_title]["cover_url"]:
                        self.songs_map[std_title]["cover_url"] = arc['pic']
                
                current_page += 1
                time.sleep(1)
            except Exception as e:
                print(f"❌ 运行中发生错误: {e}")
                break

        # 写入文件
        if len(self.songs_map) > 0:
            os.makedirs('./public/data', exist_ok=True)
            with open('./public/data/database.json', 'w', encoding='utf-8') as f:
                json.dump(list(self.songs_map.values()), f, ensure_ascii=False, indent=2)
            print(f"✅ 处理完成，共计 {len(self.songs_map)} 首曲目")

if __name__ == "__main__":
    VLinkSyncEngine().run()