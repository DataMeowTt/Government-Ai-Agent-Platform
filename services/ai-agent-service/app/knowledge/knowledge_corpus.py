from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.catalog.canonical_indicator_catalog import list_indicators


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    type: str
    title: str
    aliases: tuple[str, ...] = ()
    definition: str = ""
    how_to_interpret: str = ""
    example: str = ""
    caveat: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def build_knowledge_corpus() -> list[KnowledgeEntry]:
    return [
        *_indicator_entries(),
        *_analytics_concept_entries(),
        *_data_source_entries(),
        _system_capability_entry(),
        _reasoning_policy_entry(),
    ]


def _indicator_entries() -> list[KnowledgeEntry]:
    entries: list[KnowledgeEntry] = []
    for indicator in list_indicators():
        definition = indicator.description_vi or f"{indicator.name_vi} là một chỉ số thuộc nhóm {indicator.category}."
        unit_text = f" Đơn vị: {indicator.unit}." if indicator.unit else ""
        how_to_interpret = _indicator_interpretation(indicator)
        caveat = _indicator_caveat(indicator)
        entries.append(
            KnowledgeEntry(
                id=f"indicator:{indicator.code}",
                type="indicator",
                title=indicator.name_vi or indicator.name_en or indicator.code,
                aliases=tuple(
                    alias
                    for alias in (
                        indicator.code,
                        indicator.name_vi,
                        indicator.name_en,
                        *indicator.aliases,
                    )
                    if alias
                ),
                definition=f"{definition}{unit_text}".strip(),
                how_to_interpret=how_to_interpret,
                example=_indicator_example(indicator),
                caveat=caveat,
                metadata={
                    "code": indicator.code,
                    "name_vi": indicator.name_vi,
                    "name_en": indicator.name_en,
                    "category": indicator.category,
                    "unit": indicator.unit,
                    "supports_compare": indicator.supports_compare,
                    "supports_trend": indicator.supports_trend,
                    "supports_anomaly": indicator.supports_anomaly,
                    "used_for_cluster": indicator.used_for_cluster,
                },
            )
        )
    return entries


def _indicator_interpretation(indicator: Any) -> str:
    unit = str(indicator.unit or "").strip()
    if unit == "%":
        return (
            "Có thể đọc như tỷ lệ phần trăm để so sánh giữa quốc gia, theo thời gian hoặc với mức tham chiếu phù hợp. "
            "Mức cao/thấp cần được diễn giải theo bản chất từng chỉ số."
        )
    if unit == "0/1":
        return "Giá trị 1 thường biểu thị sự kiện xảy ra trong năm quan sát; giá trị 0 biểu thị không ghi nhận sự kiện đó."
    if unit == "ratio":
        return "Có thể đọc như một tỷ số tương đối; nên so sánh cùng thang đo và cùng định nghĩa chỉ số."
    if unit == "current US$":
        return "Có thể dùng để so sánh quy mô danh nghĩa, nhưng cần thận trọng vì chịu ảnh hưởng của giá hiện hành và tỷ giá."
    if unit == "log":
        return "Đây là thang log, phù hợp để so sánh tương đối hơn là đọc như giá trị tiền tệ trực tiếp."
    return "Có thể dùng để so sánh xu hướng, mức tương đối và độ khác biệt trong phạm vi dữ liệu hiện có."


def _indicator_example(indicator: Any) -> str:
    if indicator.code == "govdebt_GDP":
        return "Nếu nợ công/GDP tăng, quy mô nợ khu vực công đang lớn hơn so với quy mô nền kinh tế."
    if indicator.code == "inflation_cpi":
        return "Nếu lạm phát CPI cao, mặt bằng giá tiêu dùng đang tăng nhanh và sức mua hộ gia đình có thể chịu áp lực."
    if indicator.code == "unemployment_total":
        return "Nếu tỷ lệ thất nghiệp tăng, thị trường lao động có thể đang hấp thụ việc làm kém hơn."
    return f"Ví dụ, có thể hỏi xu hướng hoặc so sánh {indicator.name_vi or indicator.code} giữa các quốc gia trong một giai đoạn cụ thể."


def _indicator_caveat(indicator: Any) -> str:
    caveats = [
        "Không nên suy ra quan hệ nhân quả chỉ từ một chỉ số mô tả.",
        "Cần kiểm tra quốc gia, giai đoạn và độ phủ dữ liệu trước khi kết luận chính sách.",
    ]
    if indicator.supports_anomaly:
        caveats.append("Bất thường thống kê là tín hiệu cần xem xét thêm, không tự động là khủng hoảng hoặc lỗi dữ liệu.")
    if indicator.used_for_cluster:
        caveats.append("Khi dùng trong phân cụm, chỉ số góp phần mô tả cấu trúc tương đối giữa các nước, không phải nhãn đánh giá tốt/xấu.")
    return " ".join(caveats)


def _analytics_concept_entries() -> list[KnowledgeEntry]:
    return [
        KnowledgeEntry(
            id="concept:trend",
            type="analytics_concept",
            title="Xu hướng",
            aliases=("trend", "xu hướng", "trend line", "đường xu hướng"),
            definition="Xu hướng mô tả chiều vận động chung của một chỉ số theo thời gian.",
            how_to_interpret="Đường xu hướng giúp nhìn phần biến động dài hơn, giảm bớt nhiễu của từng năm riêng lẻ.",
            example="Nếu tăng trưởng GDP thực có xu hướng giảm, tốc độ mở rộng của nền kinh tế có thể đang chậm lại.",
            caveat="Xu hướng không phải dự báo chắc chắn cho tương lai và không tự giải thích nguyên nhân.",
        ),
        KnowledgeEntry(
            id="concept:anomaly",
            type="analytics_concept",
            title="Bất thường thống kê",
            aliases=("anomaly", "anomaly score", "bất thường", "điểm bất thường thống kê", "outlier"),
            definition="Bất thường là quan sát lệch đáng kể so với mẫu hình thông thường của cùng chỉ số trong dữ liệu.",
            how_to_interpret="Anomaly score càng cao thường cho thấy quan sát càng lệch khỏi xu hướng hoặc mức tham chiếu thống kê.",
            example="Một năm có lạm phát CPI tăng vọt so với các năm lân cận có thể được đánh dấu là bất thường.",
            caveat="Bất thường là tín hiệu để điều tra thêm; nó không tự động chứng minh lỗi dữ liệu, khủng hoảng hay nguyên nhân cụ thể.",
        ),
        KnowledgeEntry(
            id="concept:gdp_per_capita",
            type="analytics_concept",
            title="GDP bình quân đầu người",
            aliases=("GDP bình quân đầu người", "GDP per capita", "GDP đầu người", "GDP pc", "thu nhập bình quân theo GDP"),
            definition="GDP bình quân đầu người là GDP của một nền kinh tế chia cho dân số, thường dùng để mô tả quy mô sản lượng kinh tế tính trên mỗi người.",
            how_to_interpret=(
                "Chỉ số này giúp so sánh mức sản lượng bình quân giữa quốc gia hoặc theo thời gian. "
                "Nó chịu ảnh hưởng của quy mô GDP, dân số, năng suất, cơ cấu ngành, lao động, đầu tư, thương mại và giá/tỷ giá nếu dùng giá trị danh nghĩa."
            ),
            example="Nếu GDP tăng nhanh nhưng dân số cũng tăng nhanh, GDP bình quân đầu người có thể tăng chậm hơn GDP tổng.",
            caveat="GDP bình quân đầu người không đo trực tiếp phân phối thu nhập, phúc lợi hộ gia đình hay bất bình đẳng; không nên suy ra nguyên nhân chỉ từ một năm dữ liệu.",
        ),
        KnowledgeEntry(
            id="concept:gdp_per_capita_growth",
            type="analytics_concept",
            title="Tăng trưởng GDP bình quân đầu người",
            aliases=(
                "tăng trưởng GDP bình quân đầu người",
                "GDP per capita growth",
                "tăng trưởng GDP đầu người",
                "real GDP per capita growth",
                "GDP pc growth",
            ),
            definition="Tăng trưởng GDP bình quân đầu người phản ánh tốc độ tăng sản lượng kinh tế tính trên mỗi người qua thời gian.",
            how_to_interpret=(
                "Chỉ số tăng khi GDP tăng nhanh hơn dân số hoặc khi năng suất/sản lượng trên mỗi người cải thiện. "
                "Nó có thể bị tác động bởi tăng trưởng GDP thực, tăng dân số, năng suất lao động, tỷ lệ tham gia lao động, đầu tư, dịch chuyển ngành, thương mại, du lịch hoặc kiều hối tùy bối cảnh quốc gia."
            ),
            example="Một nền kinh tế phục hồi du lịch và xuất khẩu mạnh có thể ghi nhận tăng trưởng GDP bình quân đầu người cao hơn xu hướng nếu dân số tăng chậm.",
            caveat="Tăng trưởng GDP bình quân đầu người là tín hiệu mô tả; cần kiểm tra lạm phát, dân số, cơ cấu ngành và dữ liệu nguồn trước khi kết luận nguyên nhân.",
        ),
        KnowledgeEntry(
            id="concept:growth_gap",
            type="analytics_concept",
            title="Chênh lệch tăng trưởng / Growth gap",
            aliases=(
                "chênh lệch tăng trưởng",
                "growth gap",
                "deviation from trend",
                "độ lệch xu hướng",
                "chênh lệch so với xu hướng",
                "khoảng cách tăng trưởng",
            ),
            definition="Chênh lệch tăng trưởng là độ lệch giữa một tốc độ tăng trưởng quan sát được với một chuẩn tham chiếu như xu hướng, trung bình lịch sử hoặc chỉ số liên quan.",
            how_to_interpret=(
                "Giá trị dương thường cho thấy kết quả cao hơn chuẩn tham chiếu; giá trị âm cho thấy thấp hơn chuẩn. "
                "Cần biết rõ chuẩn so sánh là gì trước khi diễn giải về hiệu quả kinh tế."
            ),
            example="Nếu tăng trưởng thực tế cao hơn xu hướng dài hạn, growth gap có thể dương và được xem là năm tăng trưởng vượt chuẩn.",
            caveat="Growth gap không tự chứng minh nguyên nhân; nó có thể đến từ cú sốc kinh tế thật, hiệu ứng nền, thay đổi dân số, cập nhật dữ liệu hoặc khác biệt phương pháp tính.",
        ),
        KnowledgeEntry(
            id="concept:gdp_pc_growth_anomaly",
            type="analytics_concept",
            title="Bất thường trong tăng trưởng GDP bình quân đầu người",
            aliases=(
                "bất thường tăng trưởng GDP bình quân đầu người",
                "bất thường GDP per capita growth",
                "bất thường chênh lệch tăng trưởng GDP bình quân đầu người",
                "GDP per capita growth anomaly",
                "GDP pc growth gap anomaly",
            ),
            definition="Bất thường trong tăng trưởng GDP bình quân đầu người là quan sát lệch mạnh so với mẫu hình thường thấy của chỉ số này trong dữ liệu.",
            how_to_interpret=(
                "Nó có thể phản ánh tăng trưởng GDP thực tăng tốc, dân số thay đổi, năng suất/đầu tư cải thiện, phục hồi ngành lớn, cú sốc thương mại/du lịch/kiều hối, "
                "hoặc khác biệt nguồn và phương pháp ghi nhận."
            ),
            example="Một quốc gia có GDP phục hồi mạnh sau năm suy giảm có thể có điểm bất thường cao vì hiệu ứng nền, ngay cả khi nguyên nhân dài hạn chưa thay đổi.",
            caveat="Bất thường là tín hiệu điều tra, không phải bằng chứng nhân quả hay kết luận dữ liệu sai; cần đối chiếu chuỗi nhiều năm và các chỉ số liên quan.",
        ),
        KnowledgeEntry(
            id="concept:cluster",
            type="analytics_concept",
            title="Cụm cấu trúc kinh tế",
            aliases=("cluster", "cụm", "structural cluster", "nhóm cấu trúc kinh tế", "phân cụm"),
            definition="Cluster là nhóm các quốc gia có hồ sơ chỉ số tương đối giống nhau trong một năm hoặc giai đoạn phân tích.",
            how_to_interpret="Các nước cùng cụm có thể tương đồng về cấu trúc kinh tế, xã hội hoặc mức phát triển theo bộ chỉ số được dùng để phân nhóm.",
            example="Một cụm có thể gồm các nền kinh tế có tỷ trọng nông nghiệp cao, đô thị hóa thấp và thu nhập bình quân thấp hơn.",
            caveat="Cluster là mô tả thống kê, không phải xếp hạng chất lượng quốc gia và phụ thuộc vào bộ chỉ số, năm dữ liệu và độ phủ.",
        ),
        KnowledgeEntry(
            id="concept:coverage",
            type="analytics_concept",
            title="Độ phủ dữ liệu",
            aliases=("coverage", "độ phủ dữ liệu", "missing data", "thiếu dữ liệu", "latest available year", "năm dữ liệu mới nhất"),
            definition="Độ phủ dữ liệu cho biết chỉ số có dữ liệu ở những quốc gia, năm và số quan sát nào.",
            how_to_interpret="Độ phủ tốt giúp so sánh đáng tin cậy hơn; thiếu dữ liệu làm kết luận kém chắc chắn hơn.",
            example="Nếu một chỉ số chỉ có dữ liệu đến năm 2020, câu hỏi cho năm 2023 có thể không trả được đầy đủ.",
            caveat="Năm dữ liệu mới nhất có thể khác nhau giữa chỉ số và quốc gia; dữ liệu nguồn cũng có thể được cập nhật hoặc hiệu chỉnh.",
        ),
        KnowledgeEntry(
            id="concept:data_limitation",
            type="analytics_concept",
            title="Giới hạn dữ liệu",
            aliases=("data limitation", "giới hạn dữ liệu", "hạn chế dữ liệu", "không đủ dữ liệu"),
            definition="Giới hạn dữ liệu là các điểm làm kết luận cần thận trọng, như thiếu quan sát, khác biệt định nghĩa hoặc độ trễ cập nhật.",
            how_to_interpret="Khi dữ liệu thiếu hoặc không đồng nhất, nên xem kết quả như tín hiệu mô tả thay vì bằng chứng đầy đủ.",
            example="Một quốc gia thiếu nhiều năm dữ liệu có thể làm xu hướng hiển thị kém ổn định.",
            caveat="Cần đối chiếu nguồn, định nghĩa chỉ số và bối cảnh quốc gia trước khi dùng cho kết luận chính sách.",
        ),
    ]


def _data_source_entries() -> list[KnowledgeEntry]:
    return [
        KnowledgeEntry(
            id="source:wdi",
            type="data_source",
            title="WDI - World Development Indicators",
            aliases=("WDI", "World Bank", "World Development Indicators", "Ngân hàng Thế giới"),
            definition="WDI là bộ chỉ số phát triển của World Bank, bao phủ nhiều chủ đề kinh tế - xã hội theo quốc gia và thời gian.",
            how_to_interpret="Trong hệ thống này, WDI được dùng làm một nguồn đầu vào cho các chỉ số phát triển, vĩ mô và xã hội khi phù hợp với hợp đồng chỉ số.",
            example="Các chỉ số như lạm phát CPI, thất nghiệp hoặc một số biến xã hội có thể lấy từ WDI khi dữ liệu phù hợp.",
            caveat="Dữ liệu WDI có thể được cập nhật, hiệu chỉnh và có độ phủ khác nhau giữa quốc gia/chỉ số.",
        ),
        KnowledgeEntry(
            id="source:faostat",
            type="data_source",
            title="FAOSTAT / FAO",
            aliases=("FAOSTAT", "FAO", "fao_macro", "Macro-Statistics Key Indicators"),
            definition="FAOSTAT là hệ thống dữ liệu thống kê của FAO, trong dự án được dùng cho nhóm chỉ số macro/structural khi phù hợp.",
            how_to_interpret="Nguồn này bổ sung dữ liệu thống kê kinh tế và cấu trúc, đặc biệt khi hợp đồng chỉ số ưu tiên hoặc cho phép dùng nguồn FAO.",
            example="Một số biến cấu trúc hoặc thống kê macro có thể được hợp nhất từ FAOSTAT/FAO.",
            caveat="Cần giữ ghi chú nguồn và chú ý khác biệt định nghĩa, đơn vị hoặc độ phủ so với nguồn khác.",
        ),
        KnowledgeEntry(
            id="source:gmd",
            type="data_source",
            title="GMD - Global Macro Database",
            aliases=("GMD", "Global Macro Database", "global macro"),
            definition="GMD là bộ dữ liệu vĩ mô toàn cầu, dùng để bổ sung các chuỗi kinh tế vĩ mô và khủng hoảng trong dự án.",
            how_to_interpret="Trong hệ thống này, GMD hỗ trợ các chỉ số tăng trưởng, tài khóa - tiền tệ, khủng hoảng và một số biến cấu trúc tùy hợp đồng chỉ số.",
            example="Các biến như nợ công/GDP, khủng hoảng hoặc tăng trưởng có thể được ưu tiên từ GMD khi phù hợp.",
            caveat="Cần tuân thủ ghi chú giấy phép/trích dẫn của nguồn và kiểm tra độ phủ theo quốc gia/năm.",
        ),
    ]


def _system_capability_entry() -> KnowledgeEntry:
    return KnowledgeEntry(
        id="system:capability_scope",
        type="system_capability",
        title="Phạm vi trả lời của hệ thống",
        aliases=("hệ thống trả lời được gì", "có thể hỏi gì", "khả năng hệ thống", "dữ liệu lấy từ đâu"),
        definition="Hệ thống hỗ trợ hỏi đáp và phân tích mô tả trên phạm vi dữ liệu WDI, FAOSTAT/FAO, GMD và các chỉ số đã được chuẩn hóa trong dự án.",
        how_to_interpret=(
            "Có thể hỏi so sánh quốc gia theo chỉ số/thời gian, xu hướng, bất thường, giải thích chỉ số, giải thích cluster, "
            "nguồn dữ liệu và giới hạn dữ liệu."
        ),
        example="Ví dụ: so sánh nợ công/GDP giữa Việt Nam và Thái Lan từ 2010 đến 2023, hoặc hỏi anomaly score là gì.",
        caveat=(
            "Không nên dùng hệ thống để dự báo tương lai khi chưa có chức năng dự báo rõ ràng, kết luận nhân quả chắc chắn, "
            "tư vấn đầu tư, tin tức chính trị hiện thời hoặc dữ liệu ngoài phạm vi nguồn hiện có."
        ),
    )


def _reasoning_policy_entry() -> KnowledgeEntry:
    return KnowledgeEntry(
        id="policy:reasoning",
        type="answer_policy",
        title="Nguyên tắc trả lời câu hỏi vì sao/nguyên nhân",
        aliases=("vì sao", "tại sao", "nguyên nhân", "phân tích", "lý do"),
        definition="Với câu hỏi nguyên nhân, dữ liệu mô tả chỉ cho thấy mẫu hình, không tự chứng minh quan hệ nhân quả.",
        how_to_interpret=(
            "Nên tách ba phần: dữ liệu cho thấy gì, một số yếu tố có thể liên quan, và điều cần kiểm chứng thêm."
        ),
        example="Nếu nợ công/GDP tăng, các yếu tố có thể liên quan gồm thâm hụt ngân sách, tăng trưởng GDP chậm hoặc chi phí vay cao hơn.",
        caveat="Dùng các cách diễn đạt như 'có thể liên quan đến', 'một số yếu tố thường gặp' và 'cần kiểm chứng thêm'.",
    )
