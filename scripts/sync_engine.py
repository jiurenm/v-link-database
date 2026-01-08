import requests
import re
import json
import time
import os

# --- 核心映射配置 ---
CHARACTER_DB = {
    # 25時
    "宵崎奏": "25時", "東雲絵名": "25時", "暁山瑞希": "25時", "朝比奈まふゆ": "25時",
    # Leo/need
    "星乃一歌": "Leo/need", "天馬咲希": "Leo/need", "望月穂波": "Leo/need", "日野森志歩": "Leo/need",
    # MMJ
    "花里みのり": "MMJ", "桐谷遥": "MMJ", "桃井愛莉": "MMJ", "日野森雫": "MMJ",
    # VBS
    "小豆沢こはね": "VBS", "白石杏": "VBS", "東雲彰人": "VBS", "青柳冬弥": "VBS",
    # WxS
    "天馬司": "WxS", "凤えむ": "WxS", "草薙寧々": "WxS", "神代類": "WxS",
    # Virtual Singers
    "初音ミク": "Virtual Singer", "镜音リン": "Virtual Singer", "镜音レン": "Virtual Singer", 
    "巡音ルカ": "Virtual Singer", "MEIKO": "Virtual Singer", "KAITO": "Virtual Singer"
}

KNOWN_GROUPS = [
    "Vivid BAD SQUAD", "ワンダーランズ×ショウタイム", "25時、ナイトコードで。", 
    "Leo/need", "MORE MORE JUMP！"
]

# --- 常量 ---
COMPOSER_BLACKLIST = ["MV", "字幕", "世界计划", "収录", "主题曲", "游戏"]

# --- 工具函数 ---
def extract_brackets(raw_title):
    """提取所有中括号内容"""
    return re.findall(r'【(.*?)】', raw_title)

class VLinkSyncEngine:
    def __init__(self, mid="13148307", season_id="1547037"):
        self.api_url = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
        self.params = {
            'mid': mid,
            'season_id': season_id,
            'sort_reverse': 'false',
            'page_size': 30, # 实际运行建议设为30
            'page_num': 1
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.songs_map = {}

    def clean_title_and_artist(self, raw_title):
        """解析标题，提取干净歌名和P主"""
        brackets = extract_brackets(raw_title)
        artist = "Unknown Producer"
        
        # 找作曲者中括号
        for b in brackets:
            if any(x in b for x in COMPOSER_BLACKLIST):
                continue
            if "×" in b or "*" in b:  # 作曲者常用 × 或 *
                artist = b
                break

        # 提取正文标题
        title_body = re.sub(r'【.*?】', '', raw_title)
        title_body = re.sub(r'（.*?）|\(.*?\)', '', title_body)  # 去括号注释
        title_body = re.sub(r'／.*$', '', title_body).strip()  # 去尾部版本说明

        # 特殊标题归一
        if title_body in ("世界", "セカイ"):
            title_body = "セカイ (世界)"

        for group in KNOWN_GROUPS:
            if artist.startswith(group):
                artist = group
                break

        return title_body, artist

    def parse_vocalists(self, raw_title):
        """解析演唱人员并判定主团体"""
        brackets = extract_brackets(raw_title)
        vocal_bracket = None
        
        for b in brackets:
            if "字幕" in b or "MV" in b or "世界计划" in b:
                continue
            # 演唱者一定包含 × 或角色名
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
        groups_found = [CHARACTER_DB[v] for v in vocalists if v in CHARACTER_DB and CHARACTER_DB[v] != "Virtual Singer"]
        vocal_type = "Sekai" if groups_found else "Virtual Singer"

        return vocalists, main_group, vocal_type

    def run(self):
        total_pages = 1
        current_page = 1
        
        while current_page <= total_pages:
            self.params['page_num'] = current_page
            print(f"📡 正在拉取第 {current_page} 页数据...")
            
            resp = requests.get(self.api_url, params=self.params, headers=self.headers).json()
            if resp['code'] != 0: 
                print("⚠️ API 请求失败或返回异常")
                break
            
            data = resp['data']
            total_pages = (data['page']['total'] // self.params['page_size']) + 1
            
            for arc in data['archives']:
                raw_title = arc['title']
                title, artist = self.clean_title_and_artist(raw_title)
                vocalists, main_group, vocal_type = self.parse_vocalists(raw_title)
                v_type_label = '3D' if '3DMV' in raw_title.upper() else '2D'
                
                # 聚合逻辑：以标题作为 key
                if title not in self.songs_map:
                    self.songs_map[title] = {
                        "id": f"pjsk_{arc['aid']}",
                        "title": title,
                        "artist": artist,
                        "is_pjsk": any(k in raw_title for k in ["世界计划", "SEKAI", "プロジェクトセカイ"]),
                        "total_views": 0,
                        "cover_url": None,  # 初始化
                        "pjsk_meta": None,
                        "versions": []
                    }
                    
                    if self.songs_map[title]["is_pjsk"]:
                        self.songs_map[title]["pjsk_meta"] = {
                            "main_group": main_group,
                            "vocalist_type": "Full" if len(set(vocalists)) > 1 else "Unit",
                            "difficulty_master": 0
                        }

                # 更新数据
                self.songs_map[title]["total_views"] += arc['stat']['view']
                self.songs_map[title]["versions"].append({
                    "type": v_type_label,
                    "label": f"{v_type_label} MV",
                    "bvid": arc['bvid'],
                    "duration": arc['duration'],
                    "vocalists": vocalists,
                    "vocal_type": vocal_type,
                    "views": arc['stat']['view']
                })

                if v_type_label == '2D':
                    self.songs_map[title]["cover_url"] = arc['pic']  # 2D 始终覆盖
                elif v_type_label == '3D' and not self.songs_map[title]["cover_url"]:
                    self.songs_map[title]["cover_url"] = arc['pic']  # 只有没有封面时才用 3D
            
            current_page += 1
            time.sleep(1) # 频率限制

        # 写入文件
        if len(self.songs_map) > 0:
            os.makedirs('./public/data', exist_ok=True)
            with open('./public/data/database.json', 'w', encoding='utf-8') as f:
                json.dump(list(self.songs_map.values()), f, ensure_ascii=False, indent=2)
            print(f"✅ 处理完成，共计 {len(self.songs_map)} 首曲目已存入 database.json")
        else:
            print("⚠️  没有数据，跳过文件写入")

if __name__ == "__main__":
    VLinkSyncEngine().run()