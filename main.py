import os
import subprocess
import requests
import platform
from dotenv import load_dotenv
from google import genai
from moviepy.editor import *
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.fx.all import crop
from moviepy.config import change_settings

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Cấu hình ImageMagick tùy theo Hệ điều hành
if platform.system() == "Windows":
    IMAGEMAGICK_BINARY = os.getenv("IMAGEMAGICK_BINARY", r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe")
else:
    IMAGEMAGICK_BINARY = os.getenv("IMAGEMAGICK_BINARY", "/usr/bin/convert")

change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})

def generate_script(topic):
    print("1. Đang tạo kịch bản với Gemini...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"Viết một kịch bản video Shorts ngắn dưới 45 giây về chủ đề: '{topic}'. Yêu cầu: Chỉ viết trực tiếp nội dung lời đọc, tuyệt đối KHÔNG kèm các hướng dẫn đạo diễn hay âm thanh. Câu văn ngắn gọn, súc tích, giật gân để thu hút người xem ngay từ giây đầu tiên."
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    
    script_text = response.text
    with open("script.txt", "w", encoding="utf-8") as f:
        f.write(script_text)
    print("=> Kịch bản đã được lưu.")
    return script_text

def generate_tts():
    print("2. Đang tạo giọng đọc với Edge-TTS...")
    subprocess.run([
        "edge-tts", 
        "-f", "script.txt", 
        "--voice", "vi-VN-HoaiMyNeural", 
        "--write-media", "audio.mp3", 
        "--write-subtitles", "subtitles.vtt"
    ], shell=True)
    print("=> Đã tạo xong audio.mp3 và subtitles.vtt")

def parse_vtt(vtt_file):
    with open(vtt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    subs = []
    i = 0
    def time_to_sec(t):
        h, m, s = t.split(':')
        return int(h)*3600 + int(m)*60 + float(s)
        
    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            times = line.split(' --> ')
            start_sec = time_to_sec(times[0])
            end_sec = time_to_sec(times[1])
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip() != '':
                text_lines.append(lines[i].strip())
                i += 1
            subs.append(((start_sec, end_sec), " ".join(text_lines)))
        else:
            i += 1
    return subs

def generate_video():
    print("3. Đang dựng video với MoviePy...")
    if not os.path.exists("bg_sample.mp4"):
        # Download sample background
        print("Tải video nền mẫu...")
        response = requests.get("https://cdn.pixabay.com/video/2020/05/25/40141-424908078_tiny.mp4")
        with open("bg_sample.mp4", "wb") as f:
            f.write(response.content)

    audio = AudioFileClip("audio.mp3")
    bg_clip = VideoFileClip("bg_sample.mp4").without_audio()

    if bg_clip.duration < audio.duration:
        bg_clip = bg_clip.loop(duration=audio.duration)
    else:
        bg_clip = bg_clip.subclip(0, audio.duration)

    w, h = bg_clip.size
    target_ratio = 9 / 16
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        bg_clip = crop(bg_clip, width=new_w, height=h, x_center=w/2, y_center=h/2)
    else:
        new_h = int(w / target_ratio)
        bg_clip = crop(bg_clip, width=w, height=new_h, x_center=w/2, y_center=h/2)

    bg_clip = bg_clip.resize((1080, 1920))

    if platform.system() == "Windows":
        font_name = 'Arial-Bold'
    else:
        font_name = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

    def make_textclip(txt):
        return TextClip(txt, font=font_name, fontsize=80, color='yellow', 
                        stroke_color='black', stroke_width=4, 
                        size=(900, None), method='caption', align='center')

    subs_data = parse_vtt("subtitles.vtt")
    subtitles = SubtitlesClip(subs_data, make_textclip)
    subtitles = subtitles.set_position(('center', 'center'))

    final_video = CompositeVideoClip([bg_clip, subtitles])
    final_video = final_video.set_audio(audio)

    print("Đang render video... Xin chờ vài phút.")
    final_video.write_videofile("final_video.mp4", fps=24, codec="libx264", audio_codec="aac", preset="fast", threads=4)
    print("=> Dựng video thành công!")

def send_to_telegram(topic):
    print("4. Đang gửi video qua Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    with open("final_video.mp4", "rb") as video_file:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": f"🎬 Video mới đã sẵn sàng!\n#Shorts"
        }
        files = {
            "video": video_file
        }
        response = requests.post(url, data=payload, files=files)
        
        if response.status_code == 200:
            print("✅ Đã gửi thành công!")
        else:
            print("❌ Lỗi Telegram:", response.text)

if __name__ == "__main__":
    if not GEMINI_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Vui lòng cấu hình file .env trước khi chạy!")
        exit(1)
        
    topic = "Top 3 sự thật rùng rợn về đại dương"
    generate_script(topic)
    generate_tts()
    generate_video()
    send_to_telegram(topic)
