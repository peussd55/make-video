## 서비스계정 드라이브에 업로드 된 파일 조회하고 삭제하는 소스코드 ##

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# 서비스 계정 키 파일 경로
SERVICE_ACCOUNT_FILE1 = 'resources/service_credential.json'
SERVICE_ACCOUNT_FILE2= 'resources/service_credential.json'

# Google Drive API 범위
SCOPES1 = ['https://www.googleapis.com/auth/drive.metadata.readonly']
SCOPES2 = ['https://www.googleapis.com/auth/drive']

# 서비스 계정 인증 및 API 클라이언트 생성
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE1, scopes=SCOPES1)
service = build('drive', 'v3', credentials=credentials)

# about.get 호출
about = service.about().get(fields="storageQuota").execute()

# 저장소 정보 출력
print("총 저장 용량:", about['storageQuota']['limit'])
print("사용된 용량:", about['storageQuota']['usage'])
print("Google Drive에서 사용된 용량:", about['storageQuota']['usageInDrive'])
print("휴지통에서 사용된 용량:", about['storageQuota']['usageInDriveTrash'])

credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE2, scopes=SCOPES2)
service = build('drive', 'v3', credentials=credentials)

# 서비스 계정이 소유한 모든 파일 검색
results = service.files().list(q="'me' in owners", fields="files(id, name, size)").execute()
files = results.get('files', [])

for file in files:
    print(f"Name: {file['name']}, Size: {file.get('size', '0')} bytes")

# # 모든 파일 삭제
# for file in files:
#     try:
#         service.files().delete(fileId=file['id']).execute()
#         #print(f"파일 {file['name']} (ID: {file['id']})가 성공적으로 삭제되었습니다.")
#     except Exception as e:
#         print(f"파일 {file['name']} (ID: {file['id']}) 삭제 중 오류 발생: {e}")