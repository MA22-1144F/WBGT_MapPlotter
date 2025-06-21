# 神奈川県のWBGT(暑さ指数)の予測値を地図上にプロットするプログラム
import geopandas as gpd
import folium
import requests
import zipfile
import os
import pandas as pd
from pathlib import Path
import time
import tempfile
import webbrowser
from datetime import datetime, timedelta
import json

class KanagawaWBGTMapper:
    
    def __init__(self, data_dir=None):
        # データディレクトリ設定
        if data_dir is None:
            try:
                home_dir = Path.home()
                self.data_dir = home_dir / "Documents" / "kanagawa_wbgt_data"
            except:
                self.data_dir = Path(tempfile.gettempdir()) / "kanagawa_wbgt_data"
        else:
            self.data_dir = Path(data_dir)
        
        # ディレクトリ作成
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            self.data_dir = Path.cwd() / "temp_wbgt_data"
            self.data_dir.mkdir(exist_ok=True)
        
        # キャッシュファイルパス
        self.cache_file = self.data_dir / "wbgt_cache.json"
        self.cache_duration = 45 * 60
        
        # 神奈川県地図データURL（国土数値情報（国土交通省））
        self.kanagawa_map_url = "https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2023/N03-20230101_14_GML.zip"
        self.kanagawa_map_filename = "N03-20230101_14_GML.zip"
        
        # WBGT予測値データURL（暑さ指数(WBGT)予測値等 電子情報提供サービス（環境省））
        self.wbgt_url = "https://www.wbgt.env.go.jp/prev15WG/dl/yohou_kanagawa.csv"
        
        # 神奈川県WBGT観測地点情報
        self.wbgt_stations = {
            "46091": {"name": "海老名", "location": "海老名市中新田", "lat": 35.4519, "lon": 139.3911},
            "46106": {"name": "横浜", "location": "横浜市中区山手町", "lat": 35.4444, "lon": 139.6380},
            "46141": {"name": "辻堂", "location": "藤沢市辻堂西海岸", "lat": 35.3197, "lon": 139.4594},
            "46166": {"name": "小田原", "location": "小田原市扇町", "lat": 35.2465, "lon": 139.1486},
            "46211": {"name": "三浦", "location": "三浦市初声町下宮田", "lat": 35.1361, "lon": 139.6122}
        }
        self.output_dir = self._setup_output_directory()
        
    def _setup_output_directory(self):
        possible_dirs = [
            Path.cwd(),
            Path.home() / "Desktop",
            Path.home() / "Documents",
            Path(tempfile.gettempdir())
        ]
        for test_dir in possible_dirs:
            try:
                test_dir.mkdir(exist_ok=True)
                test_file = test_dir / "test_output.tmp"
                test_file.write_text("test")
                test_file.unlink()
                return test_dir
            except (PermissionError, OSError):
                continue
        temp_dir = Path(tempfile.mkdtemp(prefix="wbgt_output_"))
        return temp_dir
    
    def _load_cache(self):
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                cache_time = datetime.fromisoformat(cache_data.get('timestamp', '1970-01-01'))
                if (datetime.now() - cache_time).total_seconds() < self.cache_duration:
                    return cache_data.get('data')
        except Exception:
            pass
        return None
    
    def _save_cache(self, data):
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def download_kanagawa_map_data(self):
        # 地図データをダウンロード
        zip_path = self.data_dir / self.kanagawa_map_filename
        
        if zip_path.exists() and zip_path.stat().st_size > 100000:
            return str(zip_path)
        print("地図データをダウンロード中...")
        try:
            headers = {'User-Agent': 'WBGT Map Tool/1.0 (Educational Purpose)'}
            response = requests.get(self.kanagawa_map_url, headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            return str(zip_path)
        except Exception as e:
            print(f"地図データダウンロードエラー: {e}")
            return None
    
    def load_kanagawa_map(self, zip_path):
        if not zip_path or not os.path.exists(zip_path):
            return None
        extract_dir = self.data_dir / f"extracted_{Path(zip_path).stem}"
        if not extract_dir.exists():
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
            except Exception as e:
                print(f"ZIP展開エラー: {e}")
                return None
        shapefiles = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.shp'):
                    shapefiles.append(Path(root) / file)
        if not shapefiles:
            return None
        shapefile_path = max(shapefiles, key=lambda p: p.stat().st_size)
        for encoding in ['shift_jis', 'utf-8', 'cp932']:
            try:
                gdf = gpd.read_file(shapefile_path, encoding=encoding)
                return gdf
            except:
                continue
        return None
    
    def download_wbgt_data(self, force_update=False):
        # WBGT予測値データをダウンロード
        if not force_update:
            cached_data = self._load_cache()
            if cached_data:
                return cached_data
        print("WBGT予測値データをダウンロード中...")
        try:
            headers = {
                'User-Agent': 'WBGT Map Tool/1.0 (Educational Purpose; Rate Limited)',
                'Accept': 'text/csv,text/plain',
                'Cache-Control': 'no-cache'
            }
            response = requests.get(self.wbgt_url, headers=headers, timeout=20)
            response.raise_for_status()
            csv_content = response.text
            self._save_cache(csv_content)
            return csv_content
        except Exception as e:
            print(f"WBGT予測値データダウンロードエラー: {e}")
            return None
    
    def parse_wbgt_data(self, csv_content):
        if not csv_content:
            return None, None
        try:
            lines = csv_content.strip().split('\n')
            if len(lines) < 2:
                return None, None
            # 1行目：予測日次
            time_header = lines[0].split(',')
            time_slots = []
            for i in range(2, len(time_header)):
                if time_header[i].strip():
                    time_str = time_header[i].strip()
                    if len(time_str) == 10:
                        year = int(time_str[:4])
                        month = int(time_str[4:6])
                        day = int(time_str[6:8])
                        hour = int(time_str[8:10])
                        if hour == 24:
                            dt = datetime(year, month, day) + timedelta(days=1)
                            hour = 0
                        else:
                            dt = datetime(year, month, day, hour)
                        time_slots.append(dt)
            
            # 2行目以降：各地点の時系列データ
            wbgt_data = {}
            for line in lines[1:]:
                if not line.strip():
                    continue
                elements = line.split(',')
                if len(elements) < 3:
                    continue
                station_id = elements[0].strip()
                update_time = elements[1].strip()
                if station_id in self.wbgt_stations:
                    wbgt_values = []
                    for i in range(2, min(len(elements), 2 + len(time_slots))):
                        value_str = elements[i].strip()
                        if value_str:
                            try:
                                wbgt_value = int(value_str) / 10.0
                                wbgt_values.append(wbgt_value)
                            except ValueError:
                                wbgt_values.append(None)
                        else:
                            wbgt_values.append(None)
                    wbgt_data[station_id] = {
                        'station_info': self.wbgt_stations[station_id],
                        'update_time': update_time,
                        'values': wbgt_values
                    }
            return time_slots, wbgt_data
            
        except Exception as e:
            print(f"WBGT予測値データ解析エラー: {e}")
            return None, None
    
    def get_wbgt_color(self, wbgt_value):
        # WBGTに応じた色を設定
        if wbgt_value is None:
            return 'gray', 'データなし'
        if wbgt_value >= 35:
            return 'black', '災害級の危険（35℃以上）'
        elif wbgt_value >= 33:
            return 'mediumvioletred', '極めて危険（33-35℃）'
        elif wbgt_value >= 31:
            return 'red', '危険（31-33℃）'
        elif wbgt_value >= 28:
            return 'orange', '厳重警戒（28-31℃）'
        elif wbgt_value >= 25:
            return 'gold', '警戒（25-28℃）'
        elif wbgt_value >= 21:
            return 'deepskyblue', '注意（21-25℃）'
        else:
            return 'lightblue', 'ほぼ安全（21℃未満）'
    
    def create_forecast_table(self, station_id, wbgt_data, time_slots):
        if station_id not in wbgt_data:
            return "<p>予測データがありません</p>"
        station_data = wbgt_data[station_id]
        values = station_data['values']
        table_html = '''
        <div style="max-height: 200px; overflow-y: auto; margin-top: 10px; border: 1px solid #ddd;">
            <table style="width: 100%; font-size: 11px; border-collapse: collapse;">
                <thead style="background-color: #f5f5f5; position: sticky; top: 0;">
                    <tr>
                        <th style="padding: 4px; border: 1px solid #ddd; text-align: left;">時刻</th>
                        <th style="padding: 4px; border: 1px solid #ddd; text-align: center;">WBGT</th>
                        <th style="padding: 4px; border: 1px solid #ddd; text-align: left;">危険度</th>
                    </tr>
                </thead>
                <tbody>
        '''
        
        for i, time_slot in enumerate(time_slots):
            if i < len(values):
                wbgt_value = values[i]
                if wbgt_value is not None:
                    color, level = self.get_wbgt_color(wbgt_value)
                    wbgt_text = f"{wbgt_value:.0f}℃"
                else:
                    color = 'gray'
                    level = 'データなし'
                    wbgt_text = '-'
                current_time = datetime.now()
                if time_slot <= current_time:
                    row_style = "background-color: #f0f0f0; color: #888;"
                    time_prefix = ""
                else:
                    row_style = ""
                    time_prefix = ""
                table_html += f'''
                    <tr style="{row_style}">
                        <td style="padding: 3px 5px; border: 1px solid #ddd; font-size: 10px;">
                            {time_prefix}{time_slot.strftime("%m/%d %H時")}
                        </td>
                        <td style="padding: 3px 5px; border: 1px solid #ddd; text-align: center; 
                                   color: {color}; font-weight: bold;">
                            {wbgt_text}
                        </td>
                        <td style="padding: 3px 5px; border: 1px solid #ddd; font-size: 10px; 
                                   color: {color};">
                            {level.split('（')[0]}
                        </td>
                    </tr>
                '''
        table_html += '''
                </tbody>
            </table>
        </div>
        '''  
        return table_html
    
    def create_wbgt_map(self, kanagawa_gdf, time_slots, wbgt_data):
        print("地図を作成中...")
        try:
            if kanagawa_gdf.crs != 'EPSG:4326':
                kanagawa_gdf = kanagawa_gdf.to_crs('EPSG:4326')
            bounds = kanagawa_gdf.total_bounds
            center_lon = (bounds[0] + bounds[2]) / 2
            center_lat = (bounds[1] + bounds[3]) / 2 - 0.2
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=10,
                tiles='OpenStreetMap'
            ) 
            current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
            title_html = f'''
                <h2 align="center" style="font-size:18px; margin-top: 10px;"><b>神奈川県 暑さ指数（WBGT）予測値地図</b></h2>
                <p align="center" style="font-size:12px; margin-bottom: 5px; color: #666;">
                    作成日時: {current_time}
                </p>
            '''
            m.get_root().html.add_child(folium.Element(title_html))
            folium.GeoJson(
                kanagawa_gdf,
                style_function=lambda feature: {
                    'fillColor': 'lightgray',
                    'color': 'darkgray',
                    'weight': 1,
                    'fillOpacity': 0.2,
                }
            ).add_to(m)
            if wbgt_data and time_slots:
                time_data = {}
                for time_idx, time_slot in enumerate(time_slots):
                    time_key = time_slot.strftime("%Y%m%d%H")
                    time_data[time_key] = {
                        'datetime': time_slot.strftime("%m月%d日 %H時"),
                        'full_datetime': time_slot.strftime("%Y年%m月%d日 %H時"),
                        'stations': {}
                    }
                    for station_id, data in wbgt_data.items():
                        station_info = data['station_info']
                        values = data['values']
                        update_time = data['update_time']
                        current_value = values[time_idx] if time_idx < len(values) else None
                        color, level = self.get_wbgt_color(current_value)
                        forecast_table = self.create_forecast_table(station_id, wbgt_data, time_slots)
                        time_data[time_key]['stations'][station_id] = {
                            'name': station_info['name'],
                            'location': station_info['location'],
                            'lat': station_info['lat'],
                            'lon': station_info['lon'],
                            'value': current_value,
                            'color': color,
                            'level': level,
                            'update_time': update_time,
                            'forecast_table': forecast_table
                        }
                js_data = json.dumps(time_data, ensure_ascii=False)
                first_time_key = list(time_data.keys())[0] if time_data else None
                if first_time_key:
                    for station_id, station_data in time_data[first_time_key]['stations'].items():
                        popup_content = f'''
                        <div style="font-family: Arial; font-size: 12px; width: 320px;">
                            <h4 style="margin: 5px 0; color: {station_data['color']};">{station_data['name']} 観測地点</h4>
                            <p><b>所在地:</b> {station_data['location']}</p>
                            <p><b>データ更新:</b> {station_data['update_time']}</p>
                        '''
                        if station_data['value'] is not None:
                            popup_content += f'''
                            <p><b>{time_data[first_time_key]['datetime']}のWBGT値:</b> <span style="color: {station_data['color']}; font-weight: bold; font-size: 14px;">{station_data['value']:.0f}℃</span></p>
                            <p><b>危険度:</b> <span style="color: {station_data['color']}; font-weight: bold;">{station_data['level']}</span></p>
                            '''
                        else:
                            popup_content += f'<p><b>{time_data[first_time_key]["datetime"]}のWBGT値:</b> データなし</p>'
                        popup_content += f'''
                        <h5 style="margin: 10px 0 5px 0; color: #333;">今後の予測値一覧</h5>
                        {station_data['forecast_table']}
                        </div>
                        '''
                        tooltip_text = f"{station_data['name']}: {time_data[first_time_key]['datetime']}"
                        if station_data['value'] is not None:
                            tooltip_text += f" | {station_data['value']:.0f}℃"
                        else:
                            tooltip_text += " | データなし"
                        folium.CircleMarker(
                            location=[station_data['lat'], station_data['lon']],
                            radius=12,
                            popup=folium.Popup(popup_content, max_width=350),
                            tooltip=tooltip_text,
                            color='black',
                            weight=1,
                            fillColor=station_data['color'],
                            fillOpacity=0.8
                        ).add_to(m)
                        folium.Marker(
                            location=[station_data['lat'], station_data['lon']],
                            icon=folium.DivIcon(
                                html=f'''<div style="
                                    font-size: 9px; 
                                    color: black; 
                                    font-weight: bold; 
                                    background-color: rgba(255,255,255,0.9); 
                                    border: 1px solid black; 
                                    padding: 1px 3px; 
                                    border-radius: 3px; 
                                    text-align: center;
                                    margin-top: 15px;
                                ">{station_data["name"]}</div>''',
                                icon_size=(None, None),
                                icon_anchor=(0, 0)
                            )
                        ).add_to(m)
            
            # 凡例
            legend_html = '''
            <div style="position: fixed; 
                        bottom: 120px; left: 20px; width: 200x; height: 220px; 
                        background-color: white; border:2px solid grey; z-index:9999; 
                        font-size:12px; padding: 10px; border-radius: 5px; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);">
            <p style="margin: 0 0 8px 0;"><b>WBGT危険度レベル</b></p>
            <p style="margin: 2px 0;"><span style="color: black; font-size: 16px;">●</span> 災害級の危険 (35℃以上)</p>
            <p style="margin: 2px 0;"><span style="color: mediumvioletred; font-size: 16px;">●</span> 極めて危険 (33-35℃)</p>
            <p style="margin: 2px 0;"><span style="color: red; font-size: 16px;">●</span> 危険 (31-33℃)</p>
            <p style="margin: 2px 0;"><span style="color: orange; font-size: 16px;">●</span> 厳重警戒 (28-31℃)</p>
            <p style="margin: 2px 0;"><span style="color: gold; font-size: 16px;">●</span> 警戒 (25-28℃)</p>
            <p style="margin: 2px 0;"><span style="color: deepskyblue; font-size: 16px;">●</span> 注意 (21-25℃)</p>
            <p style="margin: 2px 0;"><span style="color: lightblue; font-size: 16px;">●</span> ほぼ安全 (21℃未満)</p>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(legend_html))
            
            # 更新ボタン
            update_button_html = f'''
            <div style="position: fixed; top: 20px; right: 20px; z-index: 9999;">
                <button onclick="updateWBGTData()" 
                        style="background-color: #4CAF50; color: white; border: none; 
                               padding: 10px; border-radius: 50%; cursor: pointer; font-size: 16px;
                               width: 40px; height: 40px; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);"
                        title="データを更新">
                    ↻
                </button>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(update_button_html))
            
            # 出典表示
            copyright_html = '''
            <div style="position: fixed; bottom: 10px; left: 50%; transform: translateX(-50%); 
                        z-index: 9999; text-align: left; font-size: 9px; color: #666;
                        background-color: rgba(255,255,255,0.8); padding: 3px 8px; 
                        border-radius: 3px; max-width: 600px; width: 600px;">
                <div>国土数値情報(国土交通省)(https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-v3_1.html)よりデータを取得・加工して作成</div>
                <div>暑さ指数(WBGT)予測値等 電子情報提供サービス(環境省)(https://www.wbgt.env.go.jp/data_service.php)よりデータを取得・加工して作成</div>
            </div>
            '''
            m.get_root().html.add_child(folium.Element(copyright_html))
            
            # 時間スライダ
            slider_html = f'''
            <div style="position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%); 
                        z-index: 10000; width: 400px;">
                <div style="text-align: center; margin-bottom: 8px;">
                    <div id="timeDisplay" style="font-size: 14px; color: #333; font-weight: bold;">
                        {time_slots[0].strftime("%Y年%m月%d日 %H時") if time_slots else ""}
                    </div>
                </div>
                <input type="range" id="timeSlider" min="0" max="{len(time_slots)-1}" value="0" 
                       style="width: 100%; height: 8px; background: #ddd; border-radius: 5px; 
                              outline: none; cursor: pointer;"
                       onchange="updateDisplay(this.value)" oninput="updateTimeLabel(this.value)">
            </div>
            '''
            m.get_root().html.add_child(folium.Element(slider_html))
            
            js_code = f'''
            <style>
            .custom-div-icon {{
                background: none !important;
                border: none !important;
            }}
            .leaflet-div-icon {{
                background: transparent !important;
                border: none !important;
            }}
            </style>
            <script>
            var wbgtData = {js_data};
            var timeSlots = {json.dumps([t.strftime("%Y%m%d%H") for t in time_slots])};
            var timeLabels = {json.dumps([t.strftime("%Y年%m月%d日 %H時") for t in time_slots])};
            var currentTimeIndex = 0;
            var markers = [];
            var map = null;
            var stationMarkers = {{}};
            
            function getMapObject() {{
                if (map) return map;
                
                for (var key in window) {{
                    if (key.startsWith('map_') && window[key] && window[key]._container) {{
                        map = window[key];
                        return map;
                    }}
                }}
                return null;
            }}
            
            function getWBGTColor(value) {{
                if (value === null || value === undefined) return ['gray', 'データなし'];
                if (value >= 35) return ['black', '災害級の危険（35℃以上）'];
                if (value >= 33) return ['mediumvioletred', '極めて危険（33-35℃）'];
                if (value >= 31) return ['red', '危険（31-33℃）'];
                if (value >= 28) return ['orange', '厳重警戒（28-31℃）'];
                if (value >= 25) return ['gold', '警戒（25-28℃）'];
                if (value >= 21) return ['deepskyblue', '注意（21-25℃）'];
                return ['lightblue', 'ほぼ安全（21℃未満）'];
            }}
            
            function clearAllMarkers() {{
                var mapObj = getMapObject();
                if (!mapObj) return;
                
                markers.forEach(function(marker) {{
                    try {{
                        mapObj.removeLayer(marker);
                    }} catch(e) {{}}
                }});
                markers = [];
                
                Object.keys(stationMarkers).forEach(function(stationId) {{
                    if (stationMarkers[stationId].circle) {{
                        try {{
                            mapObj.removeLayer(stationMarkers[stationId].circle);
                        }} catch(e) {{}}
                    }}
                    if (stationMarkers[stationId].label) {{
                        try {{
                            mapObj.removeLayer(stationMarkers[stationId].label);
                        }} catch(e) {{}}
                    }}
                }});
                stationMarkers = {{}};
            }}
            
            function createMarkersForTime(timeIndex) {{
                var mapObj = getMapObject();
                if (!mapObj) {{
                    return;
                }}
                var timeKey = timeSlots[timeIndex];
                var timeData = wbgtData[timeKey];
                Object.keys(timeData.stations).forEach(function(stationId) {{
                    var station = timeData.stations[stationId];
                    var circleMarker = L.circleMarker(
                        [station.lat, station.lon],
                        {{
                            radius: 12,
                            color: 'black',
                            weight: 1,
                            fillColor: station.color,
                            fillOpacity: 0.8
                        }}
                    );
                    var tooltipText = station.name + ': ' + timeLabels[timeIndex];
                    if (station.value !== null) {{
                        tooltipText += ' | ' + station.value.toFixed(0) + '℃';
                    }} else {{
                        tooltipText += ' | データなし';
                    }}
                    circleMarker.bindTooltip(tooltipText);
                    var popupContent = '<div style="font-family: Arial; font-size: 12px; width: 320px;">';
                    popupContent += '<h4 style="margin: 5px 0;">' + station.name + '</h4>';
                    popupContent += '<p><b>所在地:</b> ' + station.location + '</p>';
                    popupContent += '<p><b>データ更新:</b> ' + station.update_time + '</p>';
                    if (station.value !== null) {{
                        popupContent += '<p><b>' + timeLabels[timeIndex] + 'のWBGT値:</b> <span style="color: ' + station.color + '; font-weight: bold; font-size: 14px;">' + station.value.toFixed(0) + '℃</span></p>';
                        popupContent += '<p><b>危険度:</b> <span style="color: ' + station.color + '; font-weight: bold;">' + station.level + '</span></p>';
                    }} else {{
                        popupContent += '<p><b>' + timeLabels[timeIndex] + 'のWBGT値:</b> データなし</p>';
                    }}
                    popupContent += '<h5 style="margin: 10px 0 5px 0; color: #333;">今後の予測値一覧</h5>';
                    popupContent += station.forecast_table;
                    popupContent += '</div>';
                    circleMarker.bindPopup(popupContent, {{maxWidth: 350}});
                    var labelMarker = L.marker(
                        [station.lat, station.lon],
                        {{
                            icon: L.divIcon({{
                                html: '<div style="font-size: 9px; color: black; font-weight: bold; background-color: rgba(255,255,255,0.9); border: 1px solid black; padding: 1px 3px; border-radius: 3px; text-align: center; margin-top: 15px;">' + station.name + '</div>',
                                iconSize: [null, null],
                                iconAnchor: [0, 0]
                            }})
                        }}
                    );
                    circleMarker.addTo(mapObj);
                    labelMarker.addTo(mapObj);
                    markers.push(circleMarker);
                    markers.push(labelMarker);
                    stationMarkers[stationId] = {{
                        circle: circleMarker,
                        label: labelMarker
                    }};
                }});
            }}
            
            function updateTimeLabel(timeIndex) {{
                var index = parseInt(timeIndex);
                document.getElementById('timeDisplay').innerHTML = timeLabels[index];
            }}
            
            function updateDisplay(timeIndex) {{
                currentTimeIndex = parseInt(timeIndex);
                document.getElementById('timeDisplay').innerHTML = timeLabels[currentTimeIndex];
                clearAllMarkers();
                createMarkersForTime(currentTimeIndex);
            }}
            
            function updateWBGTData() {{
                setTimeout(function() {{
                    location.reload();
                }}, 300);
            }}
            
            function initializeMap() {{
                var mapObj = getMapObject();
                if (mapObj) {{
                    clearAllMarkers();
                    createMarkersForTime(0);
                }} else {{
                    setTimeout(initializeMap, 1000);
                }}
            }}
            
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', function() {{
                    setTimeout(initializeMap, 1500);
                }});
            }} else {{
                setTimeout(initializeMap, 1500);
            }}
            </script>
            '''
            m.get_root().html.add_child(folium.Element(js_code))
            return m
            
        except Exception as e:
            print(f"地図作成エラー: {e}")
            return None
    
    def save_and_open_map(self, map_obj, filename="kanagawa_wbgt_map.html"):
        try:
            output_path = self.output_dir / filename
            map_obj.save(str(output_path))
            webbrowser.open(f"file://{output_path.resolve()}")
            return str(output_path)
        except Exception as e:
            print(f"保存またはブラウザ起動エラー: {e}")
            return None
