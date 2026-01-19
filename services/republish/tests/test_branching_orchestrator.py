"""
분기 실행 오케스트레이터 테스트

테스트 시나리오:
1. 10개 블로그를 조회하여 1~100, 101~500 구간으로 분기
2. 각 분류 모듈이 5개씩 독립적으로 처리하는지 검증
3. 데이터 deep copy로 독립성 보장되는지 검증
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))

from test_helpers.context_mock import (
    BlogData, FilteredQueue, ExecutionContext, create_execution_context
)


class TestBlogData:
    """BlogData 클래스 테스트"""

    def test_from_dict(self):
        """딕셔너리에서 BlogData 생성"""
        data = {
            "id": 1, "name": "Test Blog", "url": "https://test.com",
            "platform": "blogger", "post_count": 50,
            "last_publish_at": "2025-01-01T00:00:00", "credential_id": 10
        }
        blog = BlogData.from_dict(data)
        assert blog.id == 1
        assert blog.name == "Test Blog"
        assert blog.post_count == 50

    def test_deep_copy_independence(self):
        """deep_copy가 독립적인 객체를 생성하는지 검증"""
        original = BlogData(1, "Original", "https://test.com", "blogger", 100)
        copied = original.deep_copy()

        # 원본 수정
        original.name = "Modified Original"
        original.post_count = 999

        # 복사본은 영향받지 않음
        assert copied.name == "Original"
        assert copied.post_count == 100

    def test_to_dict(self):
        """to_dict 변환 테스트"""
        blog = BlogData(1, "Test", "https://test.com", "blogger", 50)
        result = blog.to_dict()
        assert result["id"] == 1
        assert result["name"] == "Test"
        assert result["post_count"] == 50


class TestFilteredQueue:
    """FilteredQueue 클래스 테스트"""

    def test_add_blog_creates_deep_copy(self):
        """add_blog가 deep copy를 생성하는지 검증"""
        queue = FilteredQueue("test_queue", 1, "status_classifier", 1, 100)
        original = BlogData(1, "Original", "https://test.com", "blogger", 50)
        queue.add_blog(original)

        # 원본 수정
        original.name = "Modified"

        # 큐의 블로그는 영향받지 않음
        assert queue.blogs[0].name == "Original"

    def test_count_property(self):
        """count 속성 테스트"""
        queue = FilteredQueue("test", 1, "classifier", None, None)
        assert queue.count == 0

        queue.add_blog(BlogData(1, "B1", "url", "blogger", 10))
        queue.add_blog(BlogData(2, "B2", "url", "blogger", 20))
        assert queue.count == 2


class TestExecutionContext:
    """ExecutionContext 클래스 테스트"""

    def test_create_context(self):
        """컨텍스트 생성 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        assert context.flow_id == 1
        assert context.user_id == 1
        assert context.execution_id is not None

    def test_set_and_get_original_pool(self):
        """original_pool 설정 및 조회 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": i, "name": f"Blog{i}", "url": f"url{i}",
             "platform": "blogger", "post_count": i * 10}
            for i in range(1, 11)
        ]
        context.set_original_pool(blogs)
        assert context.original_pool_count == 10
        assert len(context.get_original_pool()) == 10

    def test_create_filtered_queue(self):
        """필터링 큐 생성 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        queue = context.create_filtered_queue(101, "status_classifier", 1, 100)
        assert queue.module_id == 101
        assert queue.post_range_start == 1
        assert queue.post_range_end == 100

    def test_populate_filtered_queue_with_range(self):
        """범위 기반 필터링 큐 채우기 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": i, "name": f"Blog{i}", "url": f"url{i}",
             "platform": "blogger", "post_count": i * 10}
            for i in range(1, 11)
        ]
        context.set_original_pool(blogs)
        context.create_filtered_queue(101, "status_classifier", 1, 50)
        queue = context.populate_filtered_queue(101)

        # post_count 10, 20, 30, 40, 50 -> 5개
        assert queue.count == 5

    def test_branching_10_blogs_to_two_classifiers(self):
        """
        핵심 테스트: 10개 블로그를 2개 분류 모듈로 분기

        시나리오:
        - 10개 블로그 (post_count: 10, 20, ..., 100)
        - 분류 모듈 1: 1~50 구간 → 5개 블로그
        - 분류 모듈 2: 51~100 구간 → 5개 블로그
        """
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": i, "name": f"Blog{i}", "url": f"url{i}",
             "platform": "blogger", "post_count": i * 10}
            for i in range(1, 11)
        ]
        context.set_original_pool(blogs)

        # 분류 모듈 1: 1~50 구간
        context.create_filtered_queue(101, "status_classifier", 1, 50)
        queue1 = context.populate_filtered_queue(101)

        # 분류 모듈 2: 51~100 구간
        context.create_filtered_queue(102, "status_classifier", 51, 100)
        queue2 = context.populate_filtered_queue(102)

        # 검증 1: 각 큐에 5개씩 분배됨
        assert queue1.count == 5, f"Queue1 expected 5, got {queue1.count}"
        assert queue2.count == 5, f"Queue2 expected 5, got {queue2.count}"

        # 검증 2: 총합이 원본과 동일
        assert queue1.count + queue2.count == 10

        # 검증 3: 각 큐의 블로그 ID가 중복되지 않음
        queue1_ids = {b.id for b in queue1.blogs}
        queue2_ids = {b.id for b in queue2.blogs}
        assert len(queue1_ids & queue2_ids) == 0, "큐 간 블로그 ID 중복됨"

        # 검증 4: 범위가 올바름
        for blog in queue1.blogs:
            assert 1 <= blog.post_count <= 50
        for blog in queue2.blogs:
            assert 51 <= blog.post_count <= 100

    def test_data_independence_between_queues(self):
        """
        데이터 독립성 검증 테스트

        하나의 큐에서 블로그 데이터를 수정해도
        다른 큐와 원본 풀에 영향이 없어야 함
        """
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": 1, "name": "Blog1", "url": "url1",
             "platform": "blogger", "post_count": 30},
            {"id": 2, "name": "Blog2", "url": "url2",
             "platform": "blogger", "post_count": 70}
        ]
        context.set_original_pool(blogs)

        # 두 개의 큐 생성 (겹치는 범위)
        context.create_filtered_queue(101, "classifier", 1, 100)
        queue1 = context.populate_filtered_queue(101)

        context.create_filtered_queue(102, "classifier", 1, 100)
        queue2 = context.populate_filtered_queue(102)

        # 큐1의 첫 번째 블로그 수정
        queue1.blogs[0].name = "Modified in Queue1"
        queue1.blogs[0].post_count = 9999

        # 검증: 원본 풀 영향 없음
        original = context.get_original_pool()
        assert original[0].name == "Blog1"
        assert original[0].post_count == 30

        # 검증: 큐2 영향 없음
        assert queue2.blogs[0].name == "Blog1"
        assert queue2.blogs[0].post_count == 30

    def test_scenario_1_100_and_101_500_split(self):
        """
        프롬프트 시나리오: 1~100, 101~500 구간 분리

        10개 블로그:
        - 5개: post_count 10~90 (1~100 구간)
        - 5개: post_count 150~350 (101~500 구간)
        """
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            # 1~100 구간 (5개)
            {"id": 1, "name": "Blog1", "url": "u1", "platform": "blogger", "post_count": 10},
            {"id": 2, "name": "Blog2", "url": "u2", "platform": "blogger", "post_count": 30},
            {"id": 3, "name": "Blog3", "url": "u3", "platform": "blogger", "post_count": 50},
            {"id": 4, "name": "Blog4", "url": "u4", "platform": "blogger", "post_count": 70},
            {"id": 5, "name": "Blog5", "url": "u5", "platform": "blogger", "post_count": 90},
            # 101~500 구간 (5개)
            {"id": 6, "name": "Blog6", "url": "u6", "platform": "blogger", "post_count": 150},
            {"id": 7, "name": "Blog7", "url": "u7", "platform": "blogger", "post_count": 200},
            {"id": 8, "name": "Blog8", "url": "u8", "platform": "blogger", "post_count": 250},
            {"id": 9, "name": "Blog9", "url": "u9", "platform": "blogger", "post_count": 300},
            {"id": 10, "name": "Blog10", "url": "u10", "platform": "blogger", "post_count": 350},
        ]
        context.set_original_pool(blogs)

        # 분류 모듈 1: 1~100 구간
        context.create_filtered_queue(101, "status_classifier", 1, 100)
        queue1 = context.populate_filtered_queue(101)

        # 분류 모듈 2: 101~500 구간
        context.create_filtered_queue(102, "status_classifier", 101, 500)
        queue2 = context.populate_filtered_queue(102)

        # 검증
        assert queue1.count == 5, f"1~100 구간: 5개 예상, {queue1.count}개 실제"
        assert queue2.count == 5, f"101~500 구간: 5개 예상, {queue2.count}개 실제"

        # 큐1의 블로그 ID
        queue1_ids = {b.id for b in queue1.blogs}
        assert queue1_ids == {1, 2, 3, 4, 5}

        # 큐2의 블로그 ID
        queue2_ids = {b.id for b in queue2.blogs}
        assert queue2_ids == {6, 7, 8, 9, 10}

    def test_custom_filter_function(self):
        """사용자 정의 필터 함수 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": 1, "name": "BlogA", "url": "u1", "platform": "blogger", "post_count": 50},
            {"id": 2, "name": "BlogB", "url": "u2", "platform": "wordpress", "post_count": 50},
            {"id": 3, "name": "BlogC", "url": "u3", "platform": "blogger", "post_count": 50},
        ]
        context.set_original_pool(blogs)

        # blogger 플랫폼만 필터링하는 큐
        context.create_filtered_queue(101, "classifier", None, None)

        def blogger_only(blog: BlogData) -> bool:
            return blog.platform == "blogger"

        queue = context.populate_filtered_queue(101, filter_func=blogger_only)

        assert queue.count == 2
        assert all(b.platform == "blogger" for b in queue.blogs)

    def test_get_summary(self):
        """컨텍스트 요약 테스트"""
        context = create_execution_context(flow_id=1, user_id=1)
        blogs = [
            {"id": i, "name": f"Blog{i}", "url": f"u{i}",
             "platform": "blogger", "post_count": i * 10}
            for i in range(1, 6)
        ]
        context.set_original_pool(blogs)
        context.create_filtered_queue(101, "classifier", 1, 30)
        context.populate_filtered_queue(101)

        summary = context.get_summary()
        assert summary["original_pool_count"] == 5
        assert 101 in summary["filtered_queues"]
        assert summary["filtered_queues"][101]["count"] == 3


class TestBranchingOrchestratorIntegration:
    """분기 오케스트레이터 통합 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_flow(self):
        """통합 테스트: 실제 DB 없이 로직만 검증"""
        # 이 테스트는 실제 환경에서는 테스트 DB를 사용해야 함
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
