from flask import Flask, request, jsonify
import os
import uuid
import requests
from werkzeug.utils import secure_filename
from function import *  # 기존 함수 임포트
import time
import subprocess
from threading import Thread  # 비동기 처리를 위한 스레드 모듈

app = Flask(__name__)

# 업로드 및 출력 디렉토리 설정
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

GOOGLE_DRIVE_FOLDER_ID = get_google_drive_folder_id()

if not os.access(UPLOAD_FOLDER, os.W_OK):
    raise Exception(f"Write permission denied for directory: {UPLOAD_FOLDER}")
if not os.access(OUTPUT_FOLDER, os.W_OK):
    raise Exception(f"Write permission denied for directory: {OUTPUT_FOLDER}")

# 허용된 파일 확장자
ALLOWED_EXTENSIONS_MP4 = {'mp4'}
ALLOWED_EXTENSIONS_MP3 = {'mp3'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def download_file_from_url(url, save_dir):
    """
    주어진 URL에서 파일을 다운로드하고 로컬에 저장합니다.
    """
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        filename = secure_filename(url.split("/")[-1])
        filepath = os.path.join(save_dir, f"{uuid.uuid4()}_{filename}")
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath
    else:
        raise Exception(f"Failed to download file from {url}. Status code: {response.status_code}")

def send_webhook_response(webhook_url, data):
    """****웹훅****: 비동기적으로 웹훅 URL로 JSON 데이터를 전송"""
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send webhook: {e}")

@app.route('/process', methods=['POST'])
def process_files():
    """
    API 엔드포인트: MP4와 MP3 파일의 URL 또는 직접 업로드된 파일을 받아 최종 MP4 파일을 반환.
    """
    password = request.json.get('password')
    if not password or not validate_password(password):
        return jsonify({"error": "Unauthorized: Invalid password."}), 403

    mp4_urls = request.json.get('mp4_urls', [])             # mp4 url
    mp3_urls = request.json.get('mp3_urls', [])        
    mp3_urls = [item.split("+")[1] for item in mp3_urls]
    mp3_urls = ",".join(mp3_urls)                           
    mp3_urls = mp3_urls.split(",")                          # mp3 url
    genre = request.json.get('genre', [])                   
    genre = genre[0].split("+")[0]                          # 음악 세부장르
    webhook_url = request.json.get('webhook_url')           # ****웹훅****: 웹훅 URL 추가
    print('mp3_urls:', mp3_urls)
    print('genre:', genre)

    name = request.json.get('Name', 'output')               # 파일명
    logoSize = request.json.get('logoSize', '720')          # 로고사이즈
    pixel = request.json.get('Pixel', 'HD')                 # 화질
    

    if pixel == 'FHD':
        width, height = 1920, 1080
    else:
        width, height = 1280, 720
    fps = 15
    crf = 38

    if len(mp4_urls) != 1:
        return jsonify({"error": "Only one MP4 file is allowed."}), 400

    if not mp4_urls and 'mp4_files' not in request.files:
        return jsonify({"error": "MP4 files or URLs are required."}), 400
    if not mp3_urls and 'mp3_files' not in request.files:
        return jsonify({"error": "MP3 files or URLs are required."}), 400

    def process_task():
        """
        비동기 작업 수행 함수.
        """
        try:
            # MP4 URL 처리
            mp4_file = download_file_from_url(mp4_urls[0], UPLOAD_FOLDER)

            # MP3 URL 처리 및 병합
            saved_mp3_paths = [download_file_from_url(url, UPLOAD_FOLDER) for url in mp3_urls]
            merged_audio_path = os.path.join(OUTPUT_FOLDER, "merged_audio.mp3")
            concatenate_audios(saved_mp3_paths, merged_audio_path)

            # 최종 비디오 생성 (MP4 반복 재생 및 오버레이)
            final_output_path = os.path.join(OUTPUT_FOLDER, f"{name}.mp4")
            create_efficient_video_with_audio_overlay(
                audio_file=merged_audio_path,
                overlay_video=mp4_file,
                output_video=final_output_path,
                width=width,
                height=height,
                fps=fps,
                video_bitrate="0",
                audio_bitrate="0",
                crf=crf
            )

            # 로고 삽입
            logo_image_name = f"logo_{logoSize}.png"
            logo_image_path = os.path.join("resources", logo_image_name)
            file_id = str(uuid.uuid4())
            final_output_with_logo_path = os.path.join(OUTPUT_FOLDER, f"{name}_{file_id}.mp4")

            add_logo_to_video(
                input_video=final_output_path,
                logo_image=logo_image_path,
                output_video=final_output_with_logo_path,
                x=10,
                y=10
            )

            # Google Drive에 업로드
            drive_file_id = upload_to_drive(final_output_with_logo_path, GOOGLE_DRIVE_FOLDER_ID)
            print("File successfully uploaded to Google Drive")

            # 성공 메시지를 웹훅으로 전송
            webhook_data = {
                "message": "File successfully uploaded to Google Drive.",
                "file_id": drive_file_id,
                "file_name": f"{name}_{file_id}.mp4",
                "mp3_urls": mp3_urls,
                "mp4_urls": mp4_urls,
                "genre": genre
            }
            #print("mp3_urls", mp3_urls)
            #print("mp4_urls", mp4_urls)
            #send_webhook_response(webhook_url, webhook_data)  # ****웹훅****

        except Exception as e:
            # 에러 메시지를 웹훅으로 전송
            error_data = {"error": str(e)}
            #send_webhook_response(webhook_url, error_data)  # ****웹훅****

        finally:
            # 작업 완료 후 디렉토리 정리
            clean_directory(UPLOAD_FOLDER)
            clean_directory(OUTPUT_FOLDER)

    Thread(target=process_task).start()  # ****웹훅****: 비동기 처리 스레드 시작

    return jsonify({"message": "Processing started."}), 202  # ****웹훅****: 요청한 클라이언트에 즉시 응답

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
