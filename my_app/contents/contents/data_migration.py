import json
import os
from pathlib import Path
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataMigrator:
    def __init__(self):
        # Supabase 클라이언트 초기화
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL과 SUPABASE_KEY를 .env 파일에 설정해주세요")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Level 매핑 (대문자 → 소문자)
        self.level_mapping = {
            'Beginner': 'beginner',
            'Intermediate': 'intermediate', 
            'Advanced': 'advanced'
        }
    
    def load_json_file(self, file_path: str) -> list:
        """JSON 파일을 로드하고 리스트로 반환"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"✓ {file_path} 로드 완료: {len(data)}개 콘텐츠")
            return data
        except Exception as e:
            logger.error(f"✗ {file_path} 로드 실패: {e}")
            return []
    
    def transform_data(self, raw_data: list) -> list:
        """JSON 데이터를 데이터베이스 형식으로 변환"""
        transformed_data = []
        
        for item in raw_data:
            try:
                # Level 변환 (대문자 → 소문자)
                original_level = item.get('level', 'beginner')
                converted_level = self.level_mapping.get(original_level, original_level.lower())
                
                # 데이터 변환
                transformed_item = {
                    'card_id': item.get('card_id'),
                    'title': item.get('title'),
                    'content': item.get('content'),
                    'level': converted_level,
                    'style': item.get('style', '설명형'),
                    'media_type': item.get('media_type', '텍스트'),
                    'topic_id': item.get('topic_id'),
                    'tags': item.get('tags', [])
                }
                
                # 필수 필드 검증
                if all([transformed_item['card_id'], transformed_item['title'], 
                       transformed_item['content'], transformed_item['topic_id']]):
                    transformed_data.append(transformed_item)
                else:
                    logger.warning(f"필수 필드 누락: {item.get('card_id', 'Unknown')}")
                    
            except Exception as e:
                logger.error(f"데이터 변환 실패: {item.get('card_id', 'Unknown')} - {e}")
        
        logger.info(f"✓ 데이터 변환 완료: {len(transformed_data)}개")
        return transformed_data
    
    def upload_to_supabase(self, data: list, batch_size: int = 100):
        """변환된 데이터를 Supabase에 배치 업로드"""
        total_uploaded = 0
        total_failed = 0
        
        # 배치 단위로 업로드
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            try:
                result = self.supabase.table("contents").insert(batch).execute()
                total_uploaded += len(batch)
                logger.info(f"✓ 배치 {i//batch_size + 1} 업로드 완료: {len(batch)}개")
                
            except Exception as e:
                total_failed += len(batch)
                logger.error(f"✗ 배치 {i//batch_size + 1} 업로드 실패: {e}")
                
                # 개별 업로드 시도
                for item in batch:
                    try:
                        self.supabase.table("contents").insert(item).execute()
                        total_uploaded += 1
                        total_failed -= 1
                    except Exception as individual_error:
                        logger.error(f"✗ 개별 업로드 실패 {item['card_id']}: {individual_error}")
        
        logger.info(f"업로드 완료 - 성공: {total_uploaded}, 실패: {total_failed}")
        return total_uploaded, total_failed
    
    def migrate_specific_file(self, file_path: str):
        """특정 JSON 파일 하나만 마이그레이션"""
        if not os.path.exists(file_path):
            logger.error(f"파일을 찾을 수 없습니다: {file_path}")
            return False
        
        logger.info(f"특정 파일 마이그레이션 시작: {file_path}")
        
        # 파일 로드 및 변환
        raw_data = self.load_json_file(file_path)
        if not raw_data:
            logger.error("데이터를 로드할 수 없습니다")
            return False
        
        transformed_data = self.transform_data(raw_data)
        if not transformed_data:
            logger.error("변환된 데이터가 없습니다")
            return False
        
        # 업로드
        logger.info(f"총 {len(transformed_data)}개 콘텐츠를 업로드합니다...")
        uploaded_count, failed_count = self.upload_to_supabase(transformed_data)
        
        logger.info(f"✅ 특정 파일 마이그레이션 완료: {file_path}")
        return uploaded_count > 0
    
    def migrate_specific_files(self, file_paths: list):
        """여러 특정 파일들을 마이그레이션"""
        total_success = 0
        total_failed = 0
        
        for file_path in file_paths:
            if not os.path.exists(file_path):
                logger.warning(f"파일을 찾을 수 없습니다, 건너뜀: {file_path}")
                total_failed += 1
                continue
            
            logger.info(f"처리 중: {os.path.basename(file_path)}")
            
            raw_data = self.load_json_file(file_path)
            if raw_data:
                transformed_data = self.transform_data(raw_data)
                if transformed_data:
                    uploaded_count, failed_count = self.upload_to_supabase(transformed_data)
                    if uploaded_count > 0:
                        total_success += 1
                    else:
                        total_failed += 1
                else:
                    total_failed += 1
            else:
                total_failed += 1
        
        logger.info(f"다중 파일 마이그레이션 완료 - 성공: {total_success}개 파일, 실패: {total_failed}개 파일")
        return total_success, total_failed
    
    def migrate_contents_folder(self, contents_folder: str):
        """contents 폴더의 모든 JSON 파일을 마이그레이션"""
        contents_path = Path(contents_folder)
        
        if not contents_path.exists():
            logger.error(f"폴더를 찾을 수 없습니다: {contents_folder}")
            return
        
        # JSON 파일 찾기
        json_files = list(contents_path.glob("contents_*.json"))
        
        if not json_files:
            logger.warning("contents_*.json 파일을 찾을 수 없습니다")
            return
        
        all_data = []
        
        # 각 JSON 파일 처리
        for json_file in json_files:
            logger.info(f"처리 중: {json_file.name}")
            raw_data = self.load_json_file(str(json_file))
            if raw_data:
                transformed_data = self.transform_data(raw_data)
                all_data.extend(transformed_data)
        
        if all_data:
            logger.info(f"총 {len(all_data)}개 콘텐츠를 업로드합니다...")
            self.upload_to_supabase(all_data)
        else:
            logger.warning("업로드할 데이터가 없습니다")

def main():
    """사용법 예시"""
    migrator = DataMigrator()
    
    # 사용법 1: 전체 폴더 마이그레이션
    # contents_folder = "."
    # migrator.migrate_contents_folder(contents_folder)
    
    # 사용법 2: 특정 파일 하나만 마이그레이션
    # specific_file = "contents_금융.json"
    # migrator.migrate_specific_file(specific_file)
    
    # 사용법 3: 여러 특정 파일들 마이그레이션
    # specific_files = ["contents_경제.json", "contents_사회.json"]
    # migrator.migrate_specific_files(specific_files)
    
    # 현재 설정: 전체 폴더 마이그레이션 (기본값)
    specific_files = ["contents_과학.json", "contents_금융.json"]
    migrator.migrate_specific_files(specific_files)

if __name__ == "__main__":
    main()