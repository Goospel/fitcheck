"""D2 · 사진 품질 검증 — 해상도만 (PRD 5.2 · plan.md 6절)

512×768 미만은 거부한다. 인물 감지·전신 여부는 **`tests/test_vision.py` 로 갔다**
(2026-08-21). 여기는 네트워크를 안 타는 판정만 본다.

⚠️ **이 파일의 존재 이유는 EXIF다.** 폰으로 찍은 세로 사진은 픽셀을 눕혀 저장하고
   「90도 돌려서 봐라」는 태그를 따로 단다. 그걸 안 읽으면 **멀쩡한 512×768 사진이
   768×512 로 읽혀 거부된다** (docs/open-questions.md Q7 — 실측 기록이 거기 있다).
"""

from io import BytesIO

import pytest
from PIL import Image

from core.errors import AppError
from images.validate import MIN_HEIGHT, MIN_WIDTH, normalize_photo

ORIENTATION = 274   # EXIF 태그 번호


def 사진(w: int, h: int, fmt: str = "JPEG", orientation: int | None = None) -> bytes:
    img = Image.new("RGB", (w, h), (120, 90, 60))
    buf = BytesIO()
    if orientation is None:
        img.save(buf, fmt)
    else:
        exif = img.getexif()
        exif[ORIENTATION] = orientation
        img.save(buf, fmt, exif=exif)
    return buf.getvalue()


def 크기(raw: bytes) -> tuple[int, int]:
    return Image.open(BytesIO(raw)).size


class Test최소_해상도:
    """PRD 확정값 512 × 768. **하한 포함** — 정확히 512×768 은 통과한다"""

    def test_확정값이_바뀌지_않았다(self):
        assert (MIN_WIDTH, MIN_HEIGHT) == (512, 768)

    def test_딱_맞으면_통과(self):
        raw, _ = normalize_photo(사진(512, 768))
        assert 크기(raw) == (512, 768)

    def test_넉넉하면_통과(self):
        raw, _ = normalize_photo(사진(1080, 1920))
        assert 크기(raw) == (1080, 1920)

    @pytest.mark.parametrize("w,h", [(511, 768), (512, 767), (100, 100)])
    def test_한_변이라도_모자라면_거부(self, w, h):
        with pytest.raises(AppError) as e:
            normalize_photo(사진(w, h))
        assert e.value.code == "PHOTO_TOO_SMALL"

    def test_가로로_누운_사진은_거부(self):
        # 768×512 는 넓이·높이 둘 다 기준을 못 넘는다. 전신 사진이 아니다
        with pytest.raises(AppError):
            normalize_photo(사진(768, 512))


class TestEXIF_회전:
    """Q7 — 이걸 안 하면 멀쩡한 폰 사진이 거부된다"""

    def test_눕혀_저장된_세로사진이_통과한다(self):
        # 픽셀은 768×512 지만 orientation=6 이라 사용자에게는 512×768 로 보인다
        raw = 사진(768, 512, orientation=6)
        assert 크기(raw) == (768, 512)          # naive 하게 읽으면 이렇게 보이고
        결과, _ = normalize_photo(raw)          # 거부되면 안 된다
        assert 크기(결과) == (512, 768)          # 회전이 픽셀에 구워진다

    def test_회전_태그가_남지_않는다(self):
        # 남겨두면 뷰어가 한 번 더 돌려서 두 번 회전된다
        결과, _ = normalize_photo(사진(768, 512, orientation=6))
        assert Image.open(BytesIO(결과)).getexif().get(ORIENTATION) in (None, 1)

    def test_180도_태그도_처리한다(self):
        결과, _ = normalize_photo(사진(512, 768, orientation=3))
        assert 크기(결과) == (512, 768)

    def test_태그가_없으면_그대로다(self):
        결과, _ = normalize_photo(사진(512, 768))
        assert 크기(결과) == (512, 768)

    def test_회전_후에_해상도를_본다(self):
        # 돌리면 512×768 을 못 넘는 사진. 돌리기 전 크기로 통과시키면 안 된다
        with pytest.raises(AppError) as e:
            normalize_photo(사진(768, 400, orientation=6))
        assert e.value.code == "PHOTO_TOO_SMALL"


class Test받아주는_형식:
    def test_PNG_통과(self):
        raw, fmt = normalize_photo(사진(512, 768, "PNG"))
        assert fmt == "PNG"
        assert 크기(raw) == (512, 768)

    def test_JPEG_는_JPEG_로_남는다(self):
        _, fmt = normalize_photo(사진(512, 768))
        assert fmt == "JPEG"

    def test_GIF_는_거부(self):
        # 애니메이션·팔레트라 생성 모델에 그대로 못 넘긴다
        with pytest.raises(AppError) as e:
            normalize_photo(사진(512, 768, "GIF"))
        assert e.value.code == "PHOTO_FORMAT"

    def test_이미지가_아니면_거부(self):
        with pytest.raises(AppError) as e:
            normalize_photo(b"\x00\x01 this is not an image \xff")
        assert e.value.code == "PHOTO_UNREADABLE"

    def test_빈_바이트도_거부(self):
        with pytest.raises(AppError):
            normalize_photo(b"")


class Test에러가_사용자에게_보이는_모양:
    """core.errors.AppError 규격 — 직접 JSONResponse 를 만들지 않는다 (CLAUDE.md 2절)"""

    def test_400_이다(self):
        # 서버 잘못이 아니라 사용자가 다른 사진을 골라야 하는 상황이다
        with pytest.raises(AppError) as e:
            normalize_photo(사진(100, 100))
        assert e.value.status_code == 400

    def test_한국어로_알려준다(self):
        with pytest.raises(AppError) as e:
            normalize_photo(사진(100, 100))
        assert any("가" <= c <= "힣" for c in e.value.message)

    def test_필요한_크기를_알려준다(self):
        # 「사진이 작습니다」만 보면 얼마나 키워야 하는지 모른다
        with pytest.raises(AppError) as e:
            normalize_photo(사진(100, 100))
        assert "512" in e.value.message and "768" in e.value.message


class Test재사용:
    """B3(의류 사진)도 같은 함수를 부른다 — plan.md D1"""

    def test_같은_바이트를_두_번_넣어도_같은_결과(self):
        raw = 사진(600, 900)
        assert normalize_photo(raw) == normalize_photo(raw)

    def test_결과를_다시_넣어도_통과한다(self):
        # 한 번 구운 사진이 두 번째 검사에서 거부되면 재처리 경로가 막힌다
        결과, _ = normalize_photo(사진(768, 512, orientation=6))
        다시, _ = normalize_photo(결과)
        assert 크기(다시) == (512, 768)


class TestEXIF_는_통째로_떨어진다:
    """다시 굽는 김에 메타데이터가 사라진다. **덤이 아니라 지켜야 할 성질이다** —
    폰 사진의 EXIF 에는 촬영 위치(GPS)가 들어 있고, 전신 사진과 함께 저장되면
    그게 곧 「이 사람이 어디 사는지」다."""

    def test_회전_태그가_남지_않는다(self):
        결과, _ = normalize_photo(사진(768, 512, orientation=6))
        assert not Image.open(BytesIO(결과)).getexif()

    def test_GPS_가_지워진다(self):
        img = Image.new("RGB", (512, 768), (10, 20, 30))
        exif = img.getexif()
        exif[0x8825] = {1: "N", 2: (37.0, 33.0, 0.0)}    # GPSInfo — 서울 어딘가
        buf = BytesIO()
        img.save(buf, "JPEG", exif=exif)

        결과, _ = normalize_photo(buf.getvalue())
        assert 0x8825 not in Image.open(BytesIO(결과)).getexif()
