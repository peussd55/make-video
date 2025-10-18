import os
import subprocess
import psutil
import pickle
from google.oauth2.service_account import Credentials  # [추가됨]
from googleapiclient.discovery import build  # [추가됨]
from googleapiclient.http import MediaFileUpload  # [추가됨]

# Google Drive API 인증 및 업로드 관련 설정 [추가됨]
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = 'resources/service_credential.json'  # 서비스 계정 JSON 파일 경로

def authenticate_drive():  # [추가됨]
    """
    Authenticate and create a Google Drive service instance using a service account.
    """
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def delete_existing_mp4_files(service, folder_id):
    """
    지정된 Google Drive 폴더에서 모든 .mp4 파일 삭제.
    :param service: Google Drive API 클라이언트 객체
    :param folder_id: 대상 폴더 ID
    :일반 gmail계정으로는 owner권한으로 완전삭제가 가능한데 owner권한 이전은 일일히 승인을 받아야하므로 이 함수를 써서 새 파일업로드할때 기존 파일삭제하도록함.
    :일반계정 OAuth 토큰 저장해서 일일히 승인받지않고 삭제가능하게 하는 방법도있음
    """
    try:
        # 폴더 내 모든 파일 검색 (확장자가 .mp4인 파일만 필터링)
        query = f"'{folder_id}' in parents and mimeType='video/mp4'"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])

        if not files:
            print("삭제할 .mp4 파일이 없습니다.")
            return

        for file in files:
            file_id = file['id']
            file_name = file['name']
            service.files().delete(fileId=file_id).execute()
            print(f"파일 삭제됨: {file_name} (ID: {file_id})")

    except Exception as e:
        print(f".mp4 파일 삭제 중 오류 발생: {e}")

def upload_to_drive(file_path, folder_id):  # [추가됨]
    """
    Upload a file to a specific Google Drive folder.
    :param file_path: Path to the file to upload.
    :param folder_id: ID of the Google Drive folder where the file will be uploaded.
    :return: File ID of the uploaded file.
    """
    service = authenticate_drive()

    # [기존 .mp4 파일 삭제]
    delete_existing_mp4_files(service, folder_id)

    file_metadata = {
        'name': os.path.basename(file_path),  # 파일 이름
        'parents': [folder_id]  # 업로드할 폴더 ID
    }
    media = MediaFileUpload(file_path, resumable=True)
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"File uploaded successfully with ID: {uploaded_file.get('id')}")
    return uploaded_file.get('id')

# mp3 파일 불러오기
def get_audio_duration(audio_file):
    """
    Use FFmpeg to get the duration of the audio file in seconds.
    
    :param audio_file: Path to the audio file.
    :return: Duration of the audio file in seconds.
    """
    command = f"ffprobe -i {audio_file} -show_entries format=duration -v quiet -of csv=\"p=0\""
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    return float(result.stdout.strip())

# mp3 파일 병합
def concatenate_audios(audio_files, output_file):
    """
    Concatenate multiple MP3 files into a single audio file using FFmpeg.
    """
    file_list_path = "audio_list.txt"
    try:
        # Create audio_list.txt for FFmpeg concat
        with open(file_list_path, "w") as f:
            for audio in audio_files:
                f.write(f"file '{audio}'\n")
        
        # Run FFmpeg concat command
        ffmpeg_command = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list_path,
            "-c", "copy", output_file
        ]
        subprocess.run(ffmpeg_command, check=True)
    except Exception as e:
        raise Exception(f"Error in concatenate_audios: {str(e)}")
    finally:
        if os.path.exists(file_list_path):
            os.remove(file_list_path)

# 디렉토리 파일 삭제
def clean_directory(directory):
    """
    지정된 디렉토리의 모든 파일을 삭제합니다.
    """
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)  # 파일 또는 심볼릭 링크 삭제
            elif os.path.isdir(file_path):
                os.rmdir(file_path)  # 디렉토리 삭제 (비어 있어야 함)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

# mp3 + mp4 오버레이 
def create_efficient_video_with_audio_overlay(audio_file, overlay_video, output_video, width, height, fps, video_bitrate, audio_bitrate, crf):
    """
    Overlap a single MP4 file with an MP3 file and encode the final video.
    """
    try:
        # Get the duration of the audio file
        audio_duration = get_audio_duration(audio_file)

        # 오버레이 + 인코딩 (속도 느린대신 용량 작음)
        ffmpeg_command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", overlay_video,
            "-i", audio_file,
            "-shortest", "-map", "0:v", "-map", "1:a",
            "-vf", f"scale={width}:{height},fps={fps}",
            "-b:v", video_bitrate,
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-b:a", audio_bitrate, "-c:a", "aac",
            "-map_metadata", "-1",
            "-t", str(audio_duration),
            output_video
        ]
        # 단순 병합(속도 빠른대신 용량이 큼)
        # ffmpeg_command = [
        #     "ffmpeg", "-y",
        #     "-stream_loop", "-1", "-i", overlay_video,
        #     "-i", audio_file,
        #     "-shortest", "-map", "0:v", "-map", "1:a",
        #     "-c:v", "copy",  # 비디오 재인코딩 없이 복사
        #     "-c:a", "copy",  # 오디오 재인코딩 없이 복사
        #     output_video
        # ]

        subprocess.run(ffmpeg_command, check=True)
    except Exception as e:
        raise Exception(f"Error in create_efficient_video_with_audio_overlay: {str(e)}")


# 생성된 파일들을 병합하기
def concatenate_videos(video_files, output_file):
    """
    Concatenate multiple MP4 video files into a single video using FFmpeg.
    """
    file_list_path = "file_list.txt"

    try:
        # Create file_list.txt for FFmpeg concat
        with open(file_list_path, "w") as f:
            for video in video_files:
                f.write(f"file '{video}'\n")

        # Debug: Print file_list.txt content
        with open(file_list_path, "r") as f:
            print("Contents of file_list.txt:")
            print(f.read())

        # Run FFmpeg concat command
        ffmpeg_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list_path, "-c", "copy", output_file]
        print(f"Running FFmpeg command: {' '.join(ffmpeg_command)}")

        result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        #print("FFmpeg stdout:", result.stdout)
        #print("FFmpeg stderr:", result.stderr)

        if result.returncode != 0:
            raise Exception(f"FFmpeg concat command failed with exit code {result.returncode}")
    except Exception as e:
        raise Exception(f"Error in concatenate_videos: {str(e)}")
    finally:
        # Remove file_list.txt after processing
        if os.path.exists(file_list_path):
            os.remove(file_list_path)

# 로고추가
def add_logo_to_video(input_video, logo_image, output_video, x=10, y=10):
    """
    Add a logo to the input video using FFmpeg.
    :param input_video: Path to the input video file.
    :param logo_image: Path to the logo image file.
    :param output_video: Path to the output video file with the logo.
    :param x: X-coordinate for the logo position.
    :param y: Y-coordinate for the logo position.
    """
    try:
        ffmpeg_command = [
            "ffmpeg", "-i", input_video, "-i", logo_image,
            "-filter_complex", f"overlay={x}:{y}",
            "-codec:a", "copy", output_video
        ]
        subprocess.run(ffmpeg_command, check=True)
        print(f"Logo successfully added to {output_video}")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Error adding logo: {e}")
    
# Google Drive 폴더 ID를 파일에서 읽어오기 [수정됨]
def get_google_drive_folder_id():
    """
    Read the Google Drive folder ID from the resources/drive_folder_id.txt file.
    """
    folder_id_file = os.path.join("resources", "drive_folder_id.txt")
    if not os.path.exists(folder_id_file):
        raise FileNotFoundError(f"Folder ID file not found: {folder_id_file}")
    with open(folder_id_file, "r") as f:
        folder_id = f.read().strip()
        if not folder_id:
            raise ValueError("Folder ID file is empty.")
        return folder_id
    
# Password 검증 함수 [추가됨]
def validate_password(password):
    """
    Validate the password against the value stored in password.txt.
    """
    password_file = os.path.join("resources", "password.txt")
    if not os.path.exists(password_file):
        raise FileNotFoundError(f"Password file not found: {password_file}")
    
    with open(password_file, "r") as f:
        stored_password = f.read().strip()
    
    return password == stored_password


# 메모리 사용량
def log_memory_usage():
    memory_info = psutil.virtual_memory()
    print(f"Memory usage: {memory_info.used / (1024 * 1024):.2f} MB / {memory_info.total / (1024 * 1024):.2f} MB")
