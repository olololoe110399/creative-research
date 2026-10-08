"""Source-aware editorial templates and visual prompts; no source copying or LLM calls."""
from __future__ import annotations
import re
from typing import Any

def _text(value: Any) -> str:
    return str(value or "").strip()

def _slug(value: Any) -> str:
    return " ".join(re.findall(r"\w+", _text(value).casefold(), flags=re.UNICODE))

def _creative_kind(topic: str, angle: str, hook: str) -> str:
    t = " ".join([topic, angle, hook]).casefold()
    if any(x in t for x in ("schedule", "horario", "timetable", "time block", "thời khóa")):
        return "schedule"
    if any(x in t for x in ("exam", "thi cử", "test prep", "revision")):
        return "exam"
    if any(x in t for x in ("nurs", "medic", "clinical")):
        return "specialist"
    if any(x in t for x in ("note", "flashcard", "mindmap", "mind map")):
        return "notes"
    if re.search(r"\b(?:tool|app|ai|product|software)\b", t):
        return "tool"
    if any(x in t for x in ("motiv", "burnout", "tired", "procrastinat")):
        return "motivation"
    return "study_method"


_COPY_VI = {
    "schedule": (
        "4 kiểu người học, 4 cách chia lịch thực tế",
        [
            "Lịch cho người học buổi sáng: dành phiên tỉnh táo nhất cho môn khó.",
            "Lịch cho cú đêm: chốt giờ kết thúc, tránh học xuyên đêm.",
            "Lịch cho người đi làm: chia môn học thành các phiên 25 phút.",
            "Lịch tuần thi: ưu tiên chủ đề yếu và dành chỗ cho tự kiểm tra.",
            "Điều chỉnh lịch theo nhịp sống của bạn, đừng sao chép nguyên mẫu.",
        ],
    ),
    "exam": (
        "Đang gần kỳ thi? Thử kế hoạch ôn tập có kiểm tra lại",
        [
            "Liệt kê chủ đề chưa chắc trước khi bắt đầu.",
            "Ôn một phần nhỏ rồi tự trả lời khi không nhìn tài liệu.",
            "Tạo một bài kiểm tra ngắn cho chính mình.",
            "Ghi lại câu sai và quay lại vào phiên học tiếp theo.",
            "Chỉ giữ cách học nào giúp bạn giải thích được kiến thức.",
        ],
    ),
    "specialist": (
        "Khối ngành nhiều kiến thức: thử cách ôn bài bớt rối",
        [
            "Chia nội dung thành khái niệm, quy trình và ví dụ.",
            "Vẽ sơ đồ liên hệ cho những thuật ngữ hay nhầm.",
            "Tự giải thích một trường hợp đơn giản bằng lời của bạn.",
            "Kiểm tra câu trả lời với nguồn học liệu chính thức.",
            "Không coi mẹo học tập là hướng dẫn chuyên môn hoặc y tế.",
        ],
    ),
    "notes": (
        "Ghi chép nhiều nhưng khó nhớ? Đổi cách ôn thử xem",
        [
            "Sau khi học, viết lại ý chính bằng ba dòng.",
            "Biến mỗi ý thành một câu hỏi để tự kiểm tra.",
            "Vẽ một sơ đồ nối các phần có liên quan.",
            "Một ngày sau, thử trả lời khi không mở ghi chú.",
            "Chọn công cụ ghi chú bạn đã tự sử dụng và kiểm chứng.",
        ],
    ),
    "tool": (
        "Một workflow học tập 4 bước để bạn tự thử",
        [
            "Chọn một bài học thật thay vì ví dụ được dựng sẵn.",
            "Gom ghi chú chính thành các khái niệm rõ ràng.",
            "Tạo câu hỏi ôn tập rồi tự kiểm tra kết quả.",
            "Sửa chỗ sai bằng tài liệu học chính thống.",
            "Chỉ giới thiệu sản phẩm nếu đã kiểm chứng chức năng và có quyền quảng bá.",
        ],
    ),
    "motivation": (
        "Không có động lực học? Hãy thử một phiên thật nhỏ",
        [
            "Chọn đúng một nhiệm vụ hoàn thành được trong 20 phút.",
            "Cất thiết bị gây xao nhãng trước khi bắt đầu.",
            "Đặt một điểm dừng, không ép bản thân học bất tận.",
            "Sau phiên học, ghi lại phần đã hiểu và phần còn vướng.",
            "Lặp lại khi phù hợp; không hứa hẹn kết quả chỉ từ một mẹo.",
        ],
    ),
    "study_method": (
        "4 thay đổi nhỏ giúp việc học có cấu trúc hơn",
        [
            "Xác định chính xác kiến thức cần nắm trong phiên này.",
            "Học một ví dụ thật trước khi ghi chép lại công thức.",
            "Tự giải thích mà không nhìn tài liệu.",
            "Dùng một bài tập ngắn để phát hiện chỗ chưa hiểu.",
            "Lưu checklist và thử lại với một môn khác.",
        ],
    ),
}

_VARIANT_SUBTYPE_HOOK_VI = {
    "student_personas": "Lịch học nào hợp từng kiểu người học?",
    "schedule_myth": "Bạn có cần một lịch học hoàn hảo, hay chỉ cần lịch hợp mình?",
    "subject_techniques": "Môn Sinh và môn Văn có nên học bằng cùng một cách?",
    "tips_wish_sooner": "Nếu học lại từ đầu, mình sẽ bỏ bốn thói quen này",
    "knowledge_habits": "Mỗi ngày 15 phút học chủ đề mới: thử lịch này",
    "clinical_study": "Cách tự kiểm tra kiến thức điều dưỡng mà không đoán liều",
    "active_recall": "Vì sao đọc lại ghi chú liên tục chưa chắc giúp bạn nhớ?",
    "exam_errors": "Thử sửa lỗi bài thi thay vì chỉ làm thêm đề",
    "note_taking": "Bạn sẽ biến một trang ghi chú thành bài tự kiểm tra thế nào?",
    "study_tool_workflow": "Bốn bước học với công cụ mà vẫn kiểm tra nguồn",
    "everyday_schedule": "Lịch học bị lệch hôm nay? Thử điều chỉnh theo phiên",
}

_VARIANT_HOOK_VI = {
    "schedule": "Lịch học nào hợp nhịp sống của bạn nhất?",
    "exam": "Tuần thi tới rồi: bạn đã có cách ôn lại bài sai chưa?",
    "specialist": "Thử quy trình 4 bước ôn môn nhiều thuật ngữ",
    "notes": "Ghi chú thế nào để tự kiểm tra lại mà không học vẹt?",
    "tool": "Thử một buổi học có ghi chú, câu hỏi và tự kiểm tra",
    "motivation": "Chỉ có 20 phút để học: bạn sẽ bắt đầu thế nào?",
    "study_method": "Bạn đã thử học bằng cách tự giải thích chưa?",
}

# Specific creative angles found in the operator's public family vocabulary.
# This is a conservative editorial translator of STRUCTURE, not automatic
# translation/copying of someone's original overlay text or medical claims.
_SUBTYPE_DRAFTS = {
    "student_personas": (
        "4 kiểu người học, 4 lịch ôn không giống nhau",
        [
            "Bạn học theo nhịp ổn định? Đặt hai phiên ngắn xen giờ nghỉ.",
            "Dễ mất tập trung? Chia bài thành khối nhỏ và đặt điểm dừng rõ.",
            "Vừa đi học vừa đi làm? Tận dụng một phiên 25 phút có mục tiêu.",
            "Muốn tăng độ khó? Dành một phiên tự kiểm tra không mở sách.",
        ],
    ),
    "schedule_myth": (
        "Không có lịch học hoàn hảo cho tất cả mọi người",
        [
            "Bắt đầu từ giờ ngủ và lịch học cố định của chính bạn.",
            "Chọn một phiên khó trước khi năng lượng xuống thấp.",
            "Chèn giờ ăn, nghỉ và vận động vào lịch, đừng chỉ lấp kín việc học.",
            "Giữ một khoảng thời gian để ôn câu sai và chỉnh lịch tuần sau.",
        ],
    ),
    "subject_techniques": (
        "Mỗi môn học nên thử một cách ôn khác nhau",
        [
            "Môn nhiều khái niệm: thử giải thích bằng ví dụ của bạn.",
            "Môn cần giải bài: làm thử câu hỏi trước khi xem lời giải.",
            "Môn có sơ đồ: tự vẽ lại quá trình mà không nhìn mẫu.",
            "Môn nhiều từ khóa: dùng flashcard và lịch ôn lặp lại.",
        ],
    ),
    "tips_wish_sooner": (
        "4 điều mình ước biết trước khi bắt đầu ôn thi",
        [
            "Đọc đi đọc lại chưa chắc bằng tự trả lời câu hỏi.",
            "Chia chủ đề theo mức độ hiểu thay vì đếm trang tài liệu.",
            "Đặt thời gian nghỉ trước khi bắt đầu phiên ôn dài.",
            "Ghi một danh sách câu sai để quyết định buổi học tiếp theo.",
        ],
    ),
    "knowledge_habits": (
        "Muốn mở rộng hiểu biết? Thử 4 thói quen học nhỏ",
        [
            "Chọn một câu hỏi mới mỗi sáng và tìm nguồn đáng tin.",
            "Xem một bài giải thích rồi tóm tắt bằng lời của bạn.",
            "Ghi lại điều chưa hiểu, không biến mẹo tìm nhanh thành sự thật.",
            "Cuối tuần, kể lại điều đã học và ghi nguồn tham khảo.",
        ],
    ),
    "clinical_study": (
        "Sinh viên điều dưỡng: ôn kiến thức chuyên môn sao cho an toàn?",
        [
            "Dùng giáo trình và tài liệu lâm sàng được phê duyệt làm nguồn.",
            "Tách công thức, đơn vị và tình huống thành các flashcard.",
            "Tự kiểm tra với bài tập có đáp án được giảng viên xác nhận.",
            "Không dùng bài đăng hoặc AI thay hướng dẫn tính liều chuyên môn.",
        ],
    ),
    "active_recall": (
        "Thử ôn một chương mà không xem lại ghi chú liên tục",
        [
            "Đọc một phần bài học để xác định ba điểm quan trọng.",
            "Đóng tài liệu và thử giải thích thành một đoạn ngắn.",
            "Tự trả lời ba câu hỏi ngắn về phần vừa học.",
            "Mở lại nguồn học liệu để sửa lỗi, rồi lên lịch kiểm tra lần hai.",
        ],
    ),
    "exam_errors": (
        "Sai câu nào, ôn lại câu đó: thử một vòng ôn có hệ thống",
        [
            "Gom năm câu bạn đã trả lời sai trong lần luyện tập gần nhất.",
            "Phân loại lỗi: thiếu khái niệm, đọc sai hay thiếu thao tác.",
            "Học lại nguyên nhân khiến bạn sai, không chỉ nhớ đáp án.",
            "Luyện câu mới cùng chủ đề và ghi số câu làm đúng.",
        ],
    ),
    "note_taking": (
        "Ghi chú để nhớ lâu hơn, không phải để nhìn cho đẹp",
        [
            "Từ mỗi trang ghi chú, rút ra ba ý chính cần nhớ.",
            "Chuyển những ý đó thành câu hỏi ôn tập.",
            "Vẽ sơ đồ bằng ví dụ do chính bạn nghĩ ra.",
            "Hôm sau tự trả lời mà không mở phần ghi chú.",
        ],
    ),
    "study_tool_workflow": (
        "Thử một workflow học bằng công cụ, nhưng tự kiểm chứng kết quả",
        [
            "Chuẩn bị một đoạn tài liệu thật do bạn có quyền sử dụng.",
            "Tóm tắt ý chính và xác nhận lại với nguồn gốc.",
            "Tạo flashcard/câu hỏi để tự kiểm tra.",
            "Chọn công cụ đã trải nghiệm thật, tránh quảng cáo tính năng chưa kiểm chứng.",
        ],
    ),
    "everyday_schedule": (
        "Một lịch học dễ sửa khi ngày hôm nay không theo kế hoạch",
        [
            "Khởi đầu bằng một mục tiêu học có thể kiểm tra kết quả.",
            "Đặt một khoảng 25 phút tập trung vào môn khó.",
            "Sau đó nghỉ rồi làm một bài kiểm tra ngắn.",
            "Dành 10 phút cập nhật lịch ngày mai theo phần còn thiếu.",
        ],
    ),
}


def _specific_subtype(topic: str, hook: str, formula: str) -> str | None:
    """Prefer an operator family-specific pattern over a generic study tip."""
    text = " ".join((topic, hook, formula)).casefold()
    if any(k in text for k in ("medication", "nursing", "clinical", "dosage", "medicamento")):
        return "clinical_study"
    if any(k in text for k in ("different student", "student type", "user personas", "tipo de estudiantes")):
        return "student_personas"
    if any(k in text for k in ("perfect study schedule", "perfecto no existe", "perfect schedule", "myth about studying")):
        return "schedule_myth"
    if any(k in text for k in ("techniques for each subject", "different subjects", "how to study for subjects", "subject-by-subject")):
        return "subject_techniques"
    if any(k in text for k in ("wish i knew", "wish i'd known", "wish i had known", "regret statement")):
        return "tips_wish_sooner"
    if any(k in text for k in ("knowledgeable across", "educado en", "all subjects that exist", "broad knowledge")):
        return "knowledge_habits"
    if any(k in text for k in ("mistakes", "past exam errors", "incorrect answers", "câu sai")):
        return "exam_errors"
    if any(k in text for k in ("active recall", "retrieval practice", "self-testing", "retrieval")):
        return "active_recall"
    if any(k in text for k in ("notetaking", "taking notes", "note taking", "flashcard")):
        return "note_taking"
    if any(k in text for k in ("productivity app", "app recommendation", "software", "ai tool")):
        return "study_tool_workflow"
    if any(k in text for k in ("schedule", "horario", "timetable")):
        return "everyday_schedule"
    return None


def _editorial_spec(
    kind: str, *, topic: str, hook: str, formula: str,
) -> tuple[str, str, list[str]]:
    subtype = _specific_subtype(topic, hook, formula)
    if subtype:
        title, steps = _SUBTYPE_DRAFTS[subtype]
        return subtype, title, steps
    title, steps = _COPY_VI.get(kind, _COPY_VI["study_method"])
    return f"general_{kind}", title, steps


_VISUAL_QUERY = {
    "study_desk_photo": "cozy study desk overhead notebook warm natural light portrait photography",
    "lifestyle_photo": "student lifestyle studying at desk warm minimal vertical photography",
    "notes_or_document": "original handwritten study notes paper planner close up vertical",
    "app_screen": "clean original mobile app mockup white background study productivity",
    "screen_recording": "study productivity app screen tutorial original UI mockup",
    "illustration": "minimal study planner editorial illustration portrait",
    "infographic": "study schedule minimal infographic editorial vertical",
    "text_overlay": "clean typographic study advice card textured neutral background",
}


def _visual_query(visual_type: Any, topic: Any) -> str:
    visual = _slug(visual_type).replace(" ", "_")
    if visual in _VISUAL_QUERY:
        return _VISUAL_QUERY[visual]
    brief = "original editorial study desk image minimal portrait"
    if "app" in _slug(topic):
        brief = "original study app mockup portrait"
    return brief


def _draft_for_role(
    kind: str, role: str, index: int, count: int,
    *, headline: str | None = None, body_steps: list[str] | None = None,
) -> str:
    default_hook, default_steps = _COPY_VI.get(kind, _COPY_VI["study_method"])
    hook = headline or default_hook
    body = body_steps or default_steps
    r = _slug(role)
    if index == 1 or "hook" in r or "intro" in r:
        return hook
    if "product" in r or "cta" in r or "reveal" in r:
        return "Lưu checklist này. Chỉ giới thiệu công cụ sau khi team dùng thử và xác minh."
    if index == count and count > 2:
        return "Bạn sẽ thử phiên bản nào? Lưu bài để thực hành rồi ghi kết quả."
    return body[(index - 2) % len(body)]


