import streamlit as st
from wbgt_module import KanagawaWBGTMapper
import streamlit.components.v1 as components

st.set_page_config(page_title="神奈川県WBGT地図", layout="wide")

# ボタンを押したら実行
if st.button("地図を生成"):
    mapper = KanagawaWBGTMapper()
    zip_path = mapper.download_kanagawa_map_data()
    kanagawa_gdf = mapper.load_kanagawa_map(zip_path)
    csv_content = mapper.download_wbgt_data(force_update=True)
    time_slots, wbgt_data = mapper.parse_wbgt_data(csv_content)
    folium_map = mapper.create_wbgt_map(kanagawa_gdf, time_slots, wbgt_data)
    
    map_path = mapper.output_dir / "kanagawa_wbgt_map.html"
    folium_map.save(str(map_path))
    
    with open(map_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # folium地図を埋め込み
    components.html(html_content, height=800)
else:
    st.info("「地図を生成」ボタンを押してください。")
