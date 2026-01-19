"""
모듈 타입 기본값 정의

Features:
- 시스템 제공 모듈 타입의 시드 데이터
- 6대 섹션 기반 카테고리 분류

6대 섹션:
- collect: 데이터 수집
- process: 콘텐츠 가공
- utility: 유틸리티
- control: 실행 제어
- deploy: 배포 및 기록
- template: 템플릿

모듈 목록:
1. 블로그 조회 (republish_blog_fetch) - collect
2. 상태 분류 (republish_status_classify) - utility
3. 액션 스케줄러 (republish_action_schedule) - control
4. 발행 (republish_publish_execute) - deploy
5. 상태 기록 (republish_status_log) - deploy
6. 재발행 기본 템플릿 (republish_default_template) - template
"""


def get_collect_module_types() -> list[dict]:
    """데이터 수집 모듈 타입 목록"""
    return [
        {
            "code": "republish_blog_fetch",
            "name": "블로그 조회",
            "description": "Flow에 연결된 블로그 목록을 조회합니다",
            "icon": "🔍",
            "category": "collect",
            "display_order": 1,
            "param_schema": {
                "type": "object",
                "properties": {
                    "filter_active_only": {
                        "type": "boolean",
                        "title": "활성 상태 블로그만 포함",
                        "default": True,
                        "description": "비활성화된 블로그는 조회에서 제외합니다"
                    },
                    "filter_platform": {
                        "type": "string",
                        "title": "플랫폼 선택",
                        "enum": ["all", "wordpress", "blogger"],
                        "default": "all",
                        "widget": "select",
                        "enumLabels": {
                            "all": "전체",
                            "wordpress": "워드프레스",
                            "blogger": "구글 블로거"
                        }
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow_id": {"type": "integer"},
                    "user_id": {"type": "integer"},
                    "module_id": {"type": "integer"}
                },
                "required": ["flow_id", "user_id"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "blogs": {"type": "array"},
                    "total_count": {"type": "integer"},
                    "fetched_at": {"type": "string"}
                }
            },
            "executor_class": "shared.modules.blog_fetcher.BlogFetcher"
        },
    ]


def get_utility_module_types() -> list[dict]:
    """유틸리티 모듈 타입 목록"""
    return [
        {
            "code": "republish_status_classify",
            "name": "상태 분류",
            "description": "누적 포스트 수가 해당 구간에 속하는 블로그만 다음 단계로 통과시킵니다",
            "icon": "📊",
            "category": "utility",
            "display_order": 1,
            "param_schema": {
                "type": "object",
                "widget": "status-classify-settings",
                "properties": {
                    "min_post_count": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 500
                    },
                    "post_range_from": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 0
                    },
                    "post_range_to": {
                        "type": "integer",
                        "default": None,
                        "minimum": 1
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "blogs": {"type": "array"}
                },
                "required": ["blogs"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "classified_blogs": {"type": "array"},
                    "grade_summary": {"type": "object"}
                }
            },
            "executor_class": "app.engine.nodes.status_classifier.StatusClassifier"
        },
        {
            "code": "republish_post_selector",
            "name": "포스트 선택",
            "description": "발행할 포스트를 선택합니다 (블로그 포스트 또는 저장된 포스트)",
            "icon": "🎯",
            "category": "utility",
            "display_order": 2,
            "param_schema": {
                "type": "object",
                "properties": {
                    "post_source": {
                        "type": "string",
                        "title": "포스트 선택 방식",
                        "enum": ["blog_posts", "saved_posts"],
                        "default": "blog_posts",
                        "widget": "select",
                        "enumLabels": {
                            "blog_posts": "블로그 포스트 (재발행)",
                            "saved_posts": "저장된 포스트 (신규 발행)"
                        },
                        "description": "재발행: 블로그에 발행된 포스트 / 신규 발행: BlogAuto에 저장된 미발행 포스트"
                    },
                    "selection_mode": {
                        "type": "string",
                        "title": "포스트 선택 기준",
                        "enum": ["oldest", "random"],
                        "default": "oldest",
                        "widget": "select",
                        "enumLabels": {
                            "oldest": "가장 오래된 포스트",
                            "random": "랜덤 추출"
                        },
                        "description": "가장 오래된 포스트: 발행일 기준 오름차순 / 랜덤: 무작위 선택"
                    },
                    "exclude_recent_days": {
                        "type": "integer",
                        "title": "최근 N일 제외",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 365,
                        "description": "최근 N일 이내에 발행/수정된 포스트는 제외합니다 (0=제외 없음)"
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "classified_blogs": {"type": "array"},
                    "user_id": {"type": "integer"}
                },
                "required": ["classified_blogs"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "selected_posts": {
                        "type": "array",
                        "description": "선택된 포스트 목록 (blog_id, post_id, post_title 등 포함)"
                    },
                    "selection_summary": {
                        "type": "object",
                        "description": "선택 결과 요약 (total, selected, skipped)"
                    }
                }
            },
            "executor_class": "app.engine.nodes.post_selector.PostSelector"
        },
    ]


def get_control_module_types() -> list[dict]:
    """실행 제어 모듈 타입 목록"""
    return [
        {
            "code": "republish_action_schedule",
            "name": "액션 스케줄러",
            "description": "재발행 작업을 활성 시간대에 맞춰 분배합니다",
            "icon": "⏰",
            "category": "control",
            "display_order": 1,
            "param_schema": {
                "type": "object",
                "widget": "action-scheduler-settings",
                "properties": {
                    "interval_mode": {
                        "type": "string",
                        "enum": ["time_based", "count_based"],
                        "default": "time_based"
                    },
                    "fixed_interval_minutes": {
                        "type": "integer",
                        "default": 60,
                        "minimum": 5,
                        "maximum": 1440
                    },
                    "max_daily_count": {
                        "type": "integer",
                        "default": 24,
                        "minimum": 0,
                        "maximum": 100
                    },
                    "daily_target_count": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "min_interval_minutes": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 5,
                        "maximum": 1440
                    },
                    "schedule_matrix": {
                        "type": "array",
                        "title": "활성 시간대 설정",
                        "widget": "schedule-matrix",
                        "default": [
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0],
                            [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
                        ],
                        "description": "월~일 × 0~24시 활성화 시간대"
                    },
                    "jitter_percent": {
                        "type": "integer",
                        "default": 20,
                        "minimum": 0,
                        "maximum": 50
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "classified_blogs": {"type": "array"},
                    "scheduled_at": {"type": "string"}
                },
                "required": ["classified_blogs"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "scheduled_actions": {"type": "array"},
                    "next_run_at": {"type": "string"}
                }
            },
            "executor_class": "shared.modules.action_scheduler.ActionScheduler"
        },
    ]


def get_deploy_module_types() -> list[dict]:
    """배포 및 기록 모듈 타입 목록"""
    return [
        {
            "code": "republish_publish_execute",
            "name": "발행",
            "description": "스케줄에 따라 블로그 포스트를 재발행합니다 (플랫폼 자동 분기)",
            "icon": "🚀",
            "category": "deploy",
            "display_order": 1,
            "param_schema": {
                "type": "object",
                "properties": {
                    "max_retry_count": {
                        "type": "integer",
                        "title": "최대 재시도 횟수",
                        "default": 3,
                        "minimum": 0,
                        "maximum": 10,
                        "description": "0으로 설정하면 재시도하지 않습니다"
                    },
                    "retry_delay_seconds": {
                        "type": "integer",
                        "title": "재시도 대기 시간 (초)",
                        "default": 60,
                        "minimum": 10,
                        "maximum": 300,
                        "description": "재시도 사이 대기 시간"
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "title": "타임아웃 (초)",
                        "default": 30,
                        "minimum": 10,
                        "maximum": 120,
                        "description": "API 호출 타임아웃"
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "scheduled_actions": {"type": "array"}
                },
                "required": ["scheduled_actions"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "executed_count": {"type": "integer"},
                    "failed_count": {"type": "integer"},
                    "execution_log": {"type": "array"}
                }
            },
            "executor_class": "shared.modules.publish_executor.PublishExecutor"
        },
        {
            "code": "republish_status_log",
            "name": "상태 기록",
            "description": "재발행 결과를 데이터베이스에 기록합니다",
            "icon": "📝",
            "category": "deploy",
            "display_order": 2,
            "param_schema": {
                "type": "object",
                "properties": {
                    "save_to_database": {
                        "type": "boolean",
                        "title": "데이터베이스에 실행 로그 기록",
                        "default": True,
                        "description": "실행 결과를 DB에 저장합니다"
                    },
                    "send_notification": {
                        "type": "boolean",
                        "title": "외부 알림 전송 (설정 시)",
                        "default": False,
                        "description": "텔레그램/슬랙 등 외부 알림을 전송합니다"
                    },
                    "retention_days": {
                        "type": "integer",
                        "title": "로그 보관 기간 (일)",
                        "default": 30,
                        "minimum": 7,
                        "maximum": 365,
                        "description": "이 기간이 지난 로그는 자동 삭제됩니다"
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "execution_log": {"type": "array"},
                    "executed_count": {"type": "integer"},
                    "failed_count": {"type": "integer"}
                },
                "required": ["execution_log"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "log_id": {"type": "integer"},
                    "logged_at": {"type": "string"}
                }
            },
            "executor_class": "shared.modules.status_logger.StatusLogger"
        },
    ]


def get_template_module_types() -> list[dict]:
    """템플릿 모듈 타입 목록"""
    return [
        {
            "code": "republish_default_template",
            "name": "재발행 기본 템플릿",
            "description": "[🔍블로그 조회] → [📊상태 분류] → [🎯포스트 선택] → [⏰액션 스케줄러] → [🚀발행] → [📝상태 기록]",
            "icon": "📋",
            "category": "template",
            "display_order": 1,
            "param_schema": {
                "type": "object",
                "properties": {
                    "workflow_guide": {
                        "type": "object",
                        "title": "워크플로우 구성",
                        "widget": "workflow-guide",
                        "readonly": True,
                        "description": "각 모듈을 클릭하여 기존 모듈을 선택하거나 새로 생성할 수 있습니다",
                        "workflow_steps": [
                            {
                                "order": 1,
                                "module_type_code": "republish_blog_fetch",
                                "icon": "🔍",
                                "name": "블로그 조회",
                                "desc": "블로그 목록 조회",
                                "module_id": None
                            },
                            {
                                "order": 2,
                                "module_type_code": "republish_status_classify",
                                "icon": "📊",
                                "name": "상태 분류",
                                "desc": "블로그 필터링",
                                "module_id": None
                            },
                            {
                                "order": 3,
                                "module_type_code": "republish_post_selector",
                                "icon": "🎯",
                                "name": "포스트 선택",
                                "desc": "발행 대상 선택",
                                "module_id": None
                            },
                            {
                                "order": 4,
                                "module_type_code": "republish_action_schedule",
                                "icon": "⏰",
                                "name": "액션 스케줄러",
                                "desc": "간격 설정",
                                "module_id": None
                            },
                            {
                                "order": 5,
                                "module_type_code": "republish_publish_execute",
                                "icon": "🚀",
                                "name": "발행",
                                "desc": "재발행 실행",
                                "module_id": None
                            },
                            {
                                "order": 6,
                                "module_type_code": "republish_status_log",
                                "icon": "📝",
                                "name": "상태 기록",
                                "desc": "결과 저장",
                                "module_id": None
                            }
                        ]
                    }
                }
            },
            "input_schema": {
                "type": "object",
                "properties": {
                    "flow_id": {"type": "integer"}
                },
                "required": ["flow_id"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "modules_created": {"type": "array"},
                    "template_applied": {"type": "boolean"}
                }
            },
            "executor_class": None,
            "is_active": True
        },
    ]


def get_all_default_types() -> list[dict]:
    """모든 기본 모듈 타입 목록 반환"""
    return (
        get_collect_module_types() +
        get_utility_module_types() +
        get_control_module_types() +
        get_deploy_module_types() +
        get_template_module_types()
    )


# 레거시 호환용 함수 (deprecated)
def get_republish_node_types() -> list[dict]:
    """재발행 노드 타입 목록 (레거시 호환)"""
    return get_all_default_types()
