"""F-10 · 사이즈 비교 — 같은 옷의 여러 사이즈를 한 응답에 담는다

A5(계약 2)를 사이즈 수만큼 돌리는 게 전부다. 리포트 모양은 손대지 않고 **중첩**해서
내보내므로, 프론트는 단일 리포트 화면에 쓰던 컴포넌트를 그대로 재사용한다.

⚠️ 새 로직은 「어느 사이즈를 추천하는가」 하나뿐이다.
"""

from core.schema import Schema
from fit.report import Body, FitReport, Garment, build_report


class SizeOption(Schema):
    size_name: str        # "M" · "L" — 의류 등록 시 받은 사이즈명 (plan.md B3)
    report: FitReport     # 계약 2 그대로. 키를 하나도 바꾸지 않는다


class SizeComparison(Schema):
    sizes: list[SizeOption]
    recommended_size: str | None   # 선호 핏 미설정이면 None


def compare_sizes(body: Body, garments: dict[str, Garment]) -> SizeComparison:
    """사이즈명 → 의류 치수 를 받아 사이즈별 리포트와 추천을 낸다.

    입력 순서가 곧 응답 순서다 — 프론트가 게이지를 왼쪽부터 이 순서로 그린다.

    **추천 규칙**: 선호 핏과의 단계 차(`gradeDistance`)가 가장 작은 사이즈.
    동점이면 여유량이 큰 쪽을 고른다 — 큰 옷을 사게 하는 편이 작은 옷보다 낫다
    (CLAUDE.md 1절 신축성 미입력 처리와 같은 원칙).

    **선호 핏이 없으면 추천하지 않는다.** 어느 쪽이 나은지 정할 근거가 없고,
    기준을 지어내지 않는다. 대신 각 리포트의 `showPreferenceCta` 가 켜져 나가므로
    프론트가 선호 핏 설정을 유도한다.
    """
    options = [
        SizeOption(size_name=이름, report=build_report(body, 옷))
        for 이름, 옷 in garments.items()
    ]

    # gradeDistance 는 선호 핏이 없으면 전 사이즈가 다 None 이다 (같은 몸이므로)
    비교가능 = [o for o in options if o.report.grade_distance is not None]
    추천 = (
        min(비교가능, key=lambda o: (abs(o.report.grade_distance), -o.report.chest_ease))
        if 비교가능
        else None
    )

    return SizeComparison(
        sizes=options,
        recommended_size=추천.size_name if 추천 is not None else None,
    )
