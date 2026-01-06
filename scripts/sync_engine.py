import requests
import re
import json
import time

# --- 配置区 ---
MID = "13148307"
SEASON_ID = "1547037"
# B站API地址
API_URL = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
OUTPUT_PATH = "./public/database.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
    'Referer': 'https://space.bilibili.com/'
}

class SyncEngine:
    def __init__(self):
        self.songs_map = {} # 用于合并不同版本的容器

    def clean_title_and_extract_meta(self, raw_title):
        """
        核心提纯逻辑：
        输入：【初音ミク／中文字幕】世界【DECO*27×堀江晶太(kemu)】【手机游戏...】
        输出：标题: 世界, 艺术家: DECO*27, 类型: 2D
        """
        # 1. 识别版本类型
        version_type = '3D' if '3DMV' in raw_title.upper() else '2D'
        
        # 2. 提取艺术家 (通常在第二个中括号内)
        artists = "Unknown"
        artist_match = re.search(r'】(.*?)【(.*?)(?=】)', raw_title)
        if artist_match:
            artists = artist_match.group(2)
        
        # 3. 提纯标题
        # 移除所有【】及其内容
        clean_title = re.sub(r'【.*?】', '', raw_title)
        # 移除常见的后缀干扰
        clean_title = re.sub(r'（.*?）|\(.*?\)|\/.*', '', clean_title).strip()
        
        # 针对 PJSK 主题曲 "世界" 的特殊归一化处理
        if clean_title == "世界" or clean_title == "セカイ":
            clean_title = "セカイ (世界)"

        return clean_title, artists, version_type

    def fetch_all(self):
        page_num = 1
        total_count = 1 # 初始占位

        print(f"开始从合集 {SEASON_ID} 同步数据...")

        while (page_num - 1) * 30 < total_count:
            params = {
                'mid': MID,
                'season_id': SEASON_ID,
                'sort_reverse': 'false',
                'page_size': 30,
                'page_num': page_num,
                'web_location': '333.1387'
            }
            
            resp = requests.get(API_URL, params=params, headers=HEADERS).json()
            if resp['code'] != 0:
                print(f"错误: {resp['message']}")
                break

            data = resp['data']
            total_count = data['page']['total']
            archives = data['archives']

            for arc in archives:
                raw_title = arc['title']
                title, artist, v_type = self.clean_title_and_extract_meta(raw_title)
                
                # 唯一ID标识（用标题作为Key进行合并）
                song_key = title

                if song_key not in self.songs_map:
                    self.songs_map[song_key] = {
                        "id": f"pjsk_{arc['aid']}",
                        "title": title,
                        "artist": artist,
                        "is_pjsk": "世界计划" in raw_title or "SEKAI" in raw_title.upper(),
                        "pjsk_meta": None, # 预留
                        "cover_url": arc['pic'],
                        "versions": []
                    }
                    
                    # 尝试注入 PJSK Meta
                    if self.songs_map[song_key]["is_pjsk"]:
                        self.songs_map[song_key]["pjsk_meta"] = {
                            "group": self.detect_group(raw_title),
                            "event_name": "", # 后续可通过VocaDB补全
                            "difficulty_master": 0 
                        }

                # 添加版本信息
                self.songs_map[song_key]["versions"].append({
                    "type": v_type,
                    "label": f"{v_type} MV",
                    "bvid": arc['bvid'],
                    "duration": arc['duration'],
                    "vocalist": "Sekai Ver." if "SEKAI ver" in raw_title else "Virtual Singer"
                })

            print(f"已处理第 {page_num} 页...")
            page_num += 1
            time.sleep(1) # 礼貌抓取

    def detect_group(self, title):
        """简单的团体检测逻辑"""
        groups = {
            "25時、ナイトコードで。": "25時、ナイトコードで。",
            "Leo/need": "Leo/need",
            "Vivid BAD SQUAD": "Vivid BAD SQUAD",
            "Wonderlands": "Wonderlands×Showtime",
            "More More Jump": "MORE MORE JUMP!"
        }
        for key, val in groups.items():
            if key in title: return val
        return "Other"

    def run(self):
        self.fetch_all()
        
        # 转换为列表输出
        final_list = list(self.songs_map.values())
        
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 同步完成！共计 {len(final_list)} 首独立曲目。")

if __name__ == "__main__":
    SyncEngine().run()
