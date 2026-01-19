"""
노드 2: 블로그 상태 분류 모듈 (재발행 특화)

Features:
- 누적 포스트 수 기반 프로파일 분류
- 프로파일별 발행 간격 및 목표 횟수 설정
- 재발행 대상 여부 판단
"""
import logging
from typing import Any, Optional

logger = logging.getLogger("status_classifier")


class RepublishProfile:
    """재발행 프로파일 상수"""
    SEEDLING = "seedling"      # 🌱 새싹: 1-100
    GROWTH = "growth"          # 🌿 성장: 101-200
    STABLE = "stable"          # 🌳 안정: 201-300
    MATURE = "mature"          # 🏛️ 성숙: 301-400
    UNLIMITED = "unlimited"    # ♾️ 무제한: 401+


# 프로파일별 설정
PROFILE_CONFIG = {
    RepublishProfile.SEEDLING: {
        "min_posts": 1,
        "max_posts": 100,
        "interval_minutes": 180,  # 3시간
        "daily_target": 4,
        "description": "🌱 새싹 (1-100개): 느린 재발행"
    },
    RepublishProfile.GROWTH: {
        "min_posts": 101,
        "max_posts": 200,
        "interval_minutes": 120,  # 2시간
        "daily_target": 6,
        "description": "🌿 성장 (101-200개): 중간 재발행"
    },
    RepublishProfile.STABLE: {
        "min_posts": 201,
        "max_posts": 300,
        "interval_minutes": 90,  # 1.5시간
        "daily_target": 8,
        "description": "🌳 안정 (201-300개): 빠른 재발행"
    },
    RepublishProfile.MATURE: {
        "min_posts": 301,
        "max_posts": 400,
        "interval_minutes": 60,  # 1시간
        "daily_target": 12,
        "description": "🏛️ 성숙 (301-400개): 집중 재발행"
    },
    RepublishProfile.UNLIMITED: {
        "min_posts": 401,
        "max_posts": None,  # 무제한
        "interval_minutes": 30,  # 30분
        "daily_target": 24,
        "description": "♾️ 무제한 (401+개): 최대 재발행"
    }
}


class StatusClassifier:
    """
    블로그 상태 분류 노드

    누적 포스트 수에 따라 재발행 프로파일을 매핑합니다.
    각 프로파일은 발행 간격과 일일 목표 횟수가 다릅니다.
    """

    def __init__(
        self,
        min_post_count: int = 10,
        custom_profiles: Optional[dict] = None
    ):
        """
        Args:
            min_post_count: 재발행 최소 포스트 수 요건
            custom_profiles: 사용자 정의 프로파일 설정 (선택)
        """
        self.min_post_count = min_post_count
        self.profiles = custom_profiles or PROFILE_CONFIG

    def execute(
        self,
        blogs: list[dict[str, Any]],
        module_settings: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        블로그 분류 실행

        Args:
            blogs: 블로그 정보 목록 (BlogFetcher 출력)
            module_settings: 모듈별 설정 (선택)

        Returns:
            StatusClassifierOutput 형식의 딕셔너리
        """
        logger.info(f"[STATUS_CLASSIFIER] 시작 | 블로그 수={len(blogs)}")

        # 모듈 설정에서 최소 포스트 수 오버라이드
        if module_settings:
            self.min_post_count = module_settings.get(
                "min_post_count", self.min_post_count
            )

        classified_blogs = []
        profile_summary = {p: 0 for p in self.profiles}

        for blog in blogs:
            result = self._classify_blog(blog)
            classified_blogs.append(result)

            if result["is_eligible"]:
                profile_summary[result["profile"]] += 1

        logger.info(
            f"[STATUS_CLASSIFIER] 완료 | "
            f"분류됨={len([c for c in classified_blogs if c['is_eligible']])}, "
            f"제외됨={len([c for c in classified_blogs if not c['is_eligible']])}"
        )

        return {
            "classified_blogs": classified_blogs,
            "profile_summary": profile_summary
        }

    def _classify_blog(self, blog: dict[str, Any]) -> dict[str, Any]:
        """개별 블로그 분류"""
        post_count = blog.get("post_count", 0)

        # 최소 포스트 수 미달
        if post_count < self.min_post_count:
            return self._create_ineligible_result(
                blog,
                f"최소 포스트 수 미달 ({post_count}/{self.min_post_count})"
            )

        # 프로파일 결정
        profile = self._determine_profile(post_count)
        config = self.profiles[profile]

        return {
            "blog": blog,
            "profile": profile,
            "interval_minutes": config["interval_minutes"],
            "daily_target": config["daily_target"],
            "is_eligible": True,
            "skip_reason": None
        }

    def _determine_profile(self, post_count: int) -> str:
        """포스트 수로 프로파일 결정"""
        for profile, config in self.profiles.items():
            min_posts = config["min_posts"]
            max_posts = config["max_posts"]

            if max_posts is None:
                # 무제한 프로파일
                if post_count >= min_posts:
                    return profile
            elif min_posts <= post_count <= max_posts:
                return profile

        # 기본값: 새싹
        return RepublishProfile.SEEDLING

    def _create_ineligible_result(
        self,
        blog: dict[str, Any],
        reason: str
    ) -> dict[str, Any]:
        """재발행 대상 아님 결과 생성"""
        return {
            "blog": blog,
            "profile": None,
            "interval_minutes": 0,
            "daily_target": 0,
            "is_eligible": False,
            "skip_reason": reason
        }

    def get_profile_info(self, profile: str) -> dict[str, Any]:
        """프로파일 정보 조회"""
        return self.profiles.get(profile, {})

    def get_all_profiles(self) -> dict[str, dict]:
        """모든 프로파일 정보 조회"""
        return self.profiles


def create_status_classifier(
    min_post_count: int = 10,
    custom_profiles: Optional[dict] = None
) -> StatusClassifier:
    """
    StatusClassifier 인스턴스 생성 팩토리 함수

    Args:
        min_post_count: 재발행 최소 포스트 수 요건
        custom_profiles: 사용자 정의 프로파일 설정

    Returns:
        StatusClassifier 인스턴스
    """
    return StatusClassifier(min_post_count, custom_profiles)
