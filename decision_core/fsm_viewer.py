import streamlit as st
from PIL import Image
import time
import os

st.set_page_config(page_title="Decision Unit FSM", layout="wide")
st.title("🚗 Decision Core State Machine — Live Viewer")

image_path = r"/home/harsh/state_ws/fsm_live.png"
placeholder = st.empty()

while True:
    if os.path.exists(image_path):
        img = Image.open(image_path)
        placeholder.image(img, caption="Current FSM State", use_container_width=True)
    else:
        placeholder.write("No FSM diagram found yet. Waiting for update...")
    time.sleep(1)

    

