import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class CanonicalIndicator:
    code: str
    name_vi: str
    name_en: str
    category: str
    unit: str
    gold_table: str
    gold_column: str
    analytics_table: str | None = None
    supports_raw: bool = True
    supports_compare: bool = True
    supports_ranking: bool = True
    supports_coverage: bool = True
    supports_trend: bool = False
    supports_anomaly: bool = False
    used_for_cluster: bool = False
    description_vi: str = ""
    description_en: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndicatorAliasMatch:
    indicator: CanonicalIndicator
    matched_alias: str
    confidence: float


ANALYTICS_SUFFIXES: tuple[str, ...] = (
    "actual",
    "trend",
    "residual",
    "slope",
    "intercept",
    "r2",
    "anomaly_score",
)


ANALYTICS_INDICATORS_BY_GOLD_TABLE: dict[str, tuple[str, ...]] = {
    "gold_growth_dynamics": (
        "rGDP_growth_YoY",
        "GDP_growth_YoY",
        "trend_deviation",
        "GDP_pc_growth_gap",
        "rolling_mean_5yr",
    ),
    "gold_fiscal_monetary": (
        "govdebt_GDP",
        "fiscal_balance_GDP",
        "real_interest_rate",
        "inflation_gap",
        "inflation_cpi",
        "tax_revenue_pct_GDP",
    ),
    "gold_crisis_risk": (
        "REER_deviation",
        "spending_efficiency",
    ),
    "gold_social_welfare": (
        "poverty_headcount",
        "poverty_change_5yr",
        "hcons_growth",
        "unemployment_total",
        "youth_unemployment_gap",
    ),
    "gold_structural_composition": (
        "GFCF_to_GDP",
        "GNI_to_GDP",
        "agri_va_share",
        "manuf_va_share",
        "food_bev_share_manuf",
    ),
}


CLUSTER_INDICATORS: tuple[str, ...] = (
    "agri_va_share",
    "manuf_va_share",
    "GFCF_to_GDP",
    "GNI_to_GDP",
    "poverty_headcount",
    "urban_pop_pct",
    "unemployment_total",
)


def _analytics_table(gold_table: str, code: str) -> str | None:
    if code in ANALYTICS_INDICATORS_BY_GOLD_TABLE.get(gold_table, ()):
        return f"analytics_{gold_table}"
    return None


def _indicator(
    code: str,
    name_vi: str,
    name_en: str,
    category: str,
    unit: str,
    gold_table: str,
    description_vi: str,
    aliases: tuple[str, ...] = (),
    description_en: str = "",
) -> CanonicalIndicator:
    analytics_table = _analytics_table(gold_table, code)
    deduped_aliases: list[str] = []
    for alias in (code, name_vi, name_en, *aliases):
        if alias and alias not in deduped_aliases:
            deduped_aliases.append(alias)

    return CanonicalIndicator(
        code=code,
        name_vi=name_vi,
        name_en=name_en,
        category=category,
        unit=unit,
        gold_table=gold_table,
        gold_column=code,
        analytics_table=analytics_table,
        supports_trend=analytics_table is not None,
        supports_anomaly=analytics_table is not None,
        used_for_cluster=code in CLUSTER_INDICATORS,
        description_vi=description_vi,
        description_en=description_en,
        aliases=tuple(deduped_aliases),
    )


_INDICATOR_ROWS: tuple[CanonicalIndicator, ...] = (
    _indicator("rGDP_growth_YoY", "Tăng trưởng GDP thực hằng năm", "Real GDP Growth Year-over-Year", "growth_dynamics", "%", "gold_growth_dynamics", "Tốc độ tăng trưởng GDP thực so với cùng kỳ năm trước.", ("real GDP growth", "real GDP growth YoY", "tăng trưởng GDP thực", "tang truong GDP thuc")),
    _indicator("rolling_mean_5yr", "Trung bình trượt 5 năm", "5-Year Rolling Mean Growth", "growth_dynamics", "%", "gold_growth_dynamics", "Trung bình trượt 5 năm của tăng trưởng GDP.", ("rolling mean 5 year", "5-year growth average", "trung bình trượt 5 năm", "trung binh truot 5 nam")),
    _indicator("trend_deviation", "Độ lệch xu hướng", "Trend Deviation", "growth_dynamics", "%", "gold_growth_dynamics", "Độ lệch của tăng trưởng thực tế so với xu hướng dài hạn.", ("trend deviation", "deviation from trend", "độ lệch xu hướng", "do lech xu huong")),
    _indicator("GDP_growth_YoY", "Tăng trưởng GDP danh nghĩa hằng năm", "Nominal GDP Growth Year-over-Year", "growth_dynamics", "%", "gold_growth_dynamics", "Tốc độ tăng trưởng GDP danh nghĩa so với năm trước.", ("nominal GDP growth", "GDP growth YoY", "tăng trưởng GDP danh nghĩa", "tang truong GDP danh nghia")),
    _indicator("GDP_growth_trend_5yr", "Xu hướng tăng trưởng GDP 5 năm", "GDP Growth Trend 5-year", "growth_dynamics", "%", "gold_growth_dynamics", "Xu hướng tăng trưởng GDP trong khung 5 năm.", ("GDP growth trend 5 year", "GDP trend", "xu hướng GDP 5 năm", "xu huong GDP 5 nam")),
    _indicator("GDP_pc_growth_gap", "Chênh lệch tăng trưởng GDP bình quân đầu người", "GDP per Capita Growth Gap", "growth_dynamics", "%", "gold_growth_dynamics", "Chênh lệch giữa tăng trưởng GDP tổng và tăng trưởng GDP bình quân đầu người.", ("GDP per capita growth gap", "GDP pc growth gap", "chênh lệch GDP bình quân", "chenh lech GDP binh quan")),
    _indicator("log_rGDP_pc_USD", "Log GDP thực bình quân đầu người", "Log Real GDP per Capita USD", "growth_dynamics", "log(USD)", "gold_growth_dynamics", "Logarit GDP thực bình quân đầu người tính bằng USD.", ("GDP per capita", "gdp_pc", "gdp per capita", "income per capita", "real GDP per capita", "log real GDP per capita", "log rGDP per capita", "GDP bình quân đầu người", "GDP binh quan dau nguoi", "GDP đầu người", "GDP dau nguoi", "thu nhập bình quân", "thu nhap binh quan")),

    _indicator("govdebt_GDP", "Nợ công/GDP", "Government Debt / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "Tỷ lệ nợ công trên GDP, thường dùng để theo dõi rủi ro tài khóa.", ("public debt", "government debt", "debt-to-GDP", "debt to GDP", "debt/GDP", "nợ công", "no cong", "nợ công/GDP", "no cong/GDP")),
    _indicator("debt_change_YoY", "Thay đổi nợ công hằng năm", "Debt Change Year-over-Year", "fiscal_monetary", "%", "gold_fiscal_monetary", "Biến động nợ công so với năm trước.", ("debt change YoY", "debt change", "biến động nợ công", "bien dong no cong")),
    _indicator("govrev_GDP", "Thu ngân sách/GDP", "Government Revenue / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "Tỷ lệ thu ngân sách chính phủ trên GDP.", ("government revenue", "revenue-to-GDP", "thu ngân sách", "thu ngan sach")),
    _indicator("govexp_GDP", "Chi ngân sách/GDP", "Government Expenditure / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "Tỷ lệ chi tiêu chính phủ trên GDP.", ("government expenditure", "expenditure-to-GDP", "chi ngân sách", "chi ngan sach")),
    _indicator("fiscal_balance_GDP", "Cân đối ngân sách/GDP", "Fiscal Balance / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "Cân đối ngân sách trên GDP, giá trị âm thường biểu thị thâm hụt.", ("fiscal balance", "fiscal balance/GDP", "budget balance", "cán cân ngân sách", "can can ngan sach", "cân đối ngân sách", "can doi ngan sach")),
    _indicator("cumulative_deficit_5yr", "Thâm hụt tích lũy 5 năm", "Cumulative Deficit 5-year", "fiscal_monetary", "%", "gold_fiscal_monetary", "Tổng thâm hụt tích lũy trong giai đoạn 5 năm.", ("cumulative deficit 5 year", "cumulative deficit", "thâm hụt tích lũy", "tham hut tich luy")),
    _indicator("ltrate", "Lãi suất dài hạn", "Long-term Interest Rate", "fiscal_monetary", "%", "gold_fiscal_monetary", "Lãi suất dài hạn phản ánh chi phí vốn dài hạn trong nền kinh tế.", ("long-term interest rate", "long-term rate", "lãi suất dài hạn", "lai suat dai han")),
    _indicator("infl", "Lạm phát theo GDP deflator", "Inflation GDP Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", "Lạm phát đo bằng GDP deflator trong bảng tài khóa - tiền tệ.", ("GDP deflator inflation rate", "infl rate", "lạm phát deflator", "lam phat deflator")),
    _indicator("real_interest_rate", "Lãi suất thực", "Real Interest Rate", "fiscal_monetary", "%", "gold_fiscal_monetary", "Lãi suất thực sau khi điều chỉnh lạm phát.", ("real interest rate", "real rate", "lãi suất thực", "lai suat thuc")),
    _indicator("tax_revenue_pct_GDP", "Thu thuế/GDP", "Tax Revenue / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "Tỷ lệ thu thuế trên GDP.", ("tax revenue", "tax-to-GDP", "tax revenue/GDP", "thu thuế", "thu thue", "thu thuế/GDP", "thu thue/GDP")),
    _indicator("inflation_cpi", "Lạm phát CPI", "Inflation CPI", "fiscal_monetary", "%", "gold_fiscal_monetary", "Lạm phát theo chỉ số giá tiêu dùng CPI.", ("CPI inflation", "consumer price inflation", "inflation CPI", "lạm phát CPI", "lam phat CPI")),
    _indicator("inflation_deflator", "Lạm phát theo deflator", "Inflation Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", "Lạm phát theo GDP deflator, phản ánh thay đổi giá của sản lượng trong nước.", ("GDP deflator", "deflator inflation", "lạm phát theo deflator", "lam phat theo deflator")),
    _indicator("inflation_gap", "Chênh lệch lạm phát", "Inflation Gap CPI minus Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", "Chênh lệch giữa lạm phát CPI và lạm phát theo GDP deflator.", ("inflation gap", "CPI deflator gap", "chênh lệch lạm phát", "chenh lech lam phat")),
    _indicator("rolling_3yr_avg_cpi", "Trung bình CPI 3 năm", "3-Year Average CPI Inflation", "fiscal_monetary", "%", "gold_fiscal_monetary", "Trung bình trượt 3 năm của lạm phát CPI.", ("3-year average CPI inflation", "rolling 3-year CPI", "trung bình CPI 3 năm", "trung binh CPI 3 nam")),

    _indicator("SovDebtCrisis", "Khủng hoảng nợ công", "Sovereign Debt Crisis", "crisis_risk", "0/1", "gold_crisis_risk", "Biến nhị phân cho biết có khủng hoảng nợ công trong năm hay không.", ("sovereign debt crisis", "debt crisis", "khủng hoảng nợ công", "khung hoang no cong")),
    _indicator("CurrencyCrisis", "Khủng hoảng tiền tệ", "Currency Crisis", "crisis_risk", "0/1", "gold_crisis_risk", "Biến nhị phân cho biết có khủng hoảng tiền tệ trong năm hay không.", ("currency crisis", "exchange rate crisis", "khủng hoảng tiền tệ", "khung hoang tien te")),
    _indicator("BankingCrisis", "Khủng hoảng ngân hàng", "Banking Crisis", "crisis_risk", "0/1", "gold_crisis_risk", "Biến nhị phân cho biết có khủng hoảng ngân hàng trong năm hay không.", ("banking crisis", "bank crisis", "khủng hoảng ngân hàng", "khung hoang ngan hang")),
    _indicator("crisis_composite", "Chỉ số khủng hoảng tổng hợp", "Crisis Composite Index", "crisis_risk", "0-3", "gold_crisis_risk", "Chỉ số tổng hợp số loại khủng hoảng xảy ra trong một năm.", ("crisis composite", "crisis index", "chỉ số khủng hoảng tổng hợp", "chi so khung hoang tong hop")),
    _indicator("crisis_any", "Có khủng hoảng", "Any Crisis Occurred", "crisis_risk", "0/1", "gold_crisis_risk", "Biến nhị phân cho biết có ít nhất một loại khủng hoảng trong năm.", ("any crisis", "crisis occurred", "có khủng hoảng", "co khung hoang")),
    _indicator("REER_deviation", "Độ lệch REER", "REER Deviation", "crisis_risk", "%", "gold_crisis_risk", "Độ lệch tỷ giá hiệu dụng thực so với xu hướng hoặc mức tham chiếu.", ("REER deviation", "real effective exchange rate deviation", "độ lệch REER", "do lech REER")),
    _indicator("spending_efficiency", "Hiệu quả chi tiêu", "Spending Efficiency", "crisis_risk", "ratio", "gold_crisis_risk", "Thước đo hiệu quả chi tiêu công.", ("spending efficiency", "public spending efficiency", "hiệu quả chi tiêu", "hieu qua chi tieu")),

    _indicator("unemployment_total", "Tỷ lệ thất nghiệp", "Unemployment Rate Total", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ thất nghiệp của toàn bộ lực lượng lao động.", ("unemployment", "unemployment rate", "total unemployment", "tỷ lệ thất nghiệp", "ti le that nghiep", "thất nghiệp", "that nghiep")),
    _indicator("unemployment_youth", "Tỷ lệ thất nghiệp thanh niên", "Youth Unemployment Rate", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ thất nghiệp trong nhóm lao động trẻ.", ("youth unemployment", "youth unemployment rate", "thất nghiệp thanh niên", "that nghiep thanh nien")),
    _indicator("youth_unemployment_gap", "Chênh lệch thất nghiệp thanh niên", "Youth Unemployment Gap", "social_welfare", "%", "gold_social_welfare", "Chênh lệch giữa thất nghiệp thanh niên và thất nghiệp tổng thể.", ("youth unemployment gap", "youth jobless gap", "chênh lệch thất nghiệp thanh niên", "chenh lech that nghiep thanh nien")),
    _indicator("youth_gap_ratio", "Tỷ lệ chênh lệch thất nghiệp thanh niên", "Youth Gap Ratio", "social_welfare", "ratio", "gold_social_welfare", "Tỷ lệ thất nghiệp thanh niên so với thất nghiệp tổng thể.", ("youth gap ratio", "youth unemployment ratio", "tỷ lệ thất nghiệp thanh niên trên tổng thể", "ty le that nghiep thanh nien tren tong the")),
    _indicator("self_employed_pct", "Tỷ lệ lao động tự doanh", "Self-Employed Percentage", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ lao động tự doanh trong tổng việc làm.", ("self-employed", "self-employed percentage", "lao động tự doanh", "lao dong tu doanh")),
    _indicator("poverty_headcount", "Tỷ lệ nghèo", "Poverty Headcount Ratio", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ dân số sống dưới ngưỡng nghèo.", ("poverty headcount", "poverty rate", "tỷ lệ nghèo", "ty le ngheo")),
    _indicator("poverty_change_5yr", "Biến động nghèo 5 năm", "Poverty Change 5-year", "social_welfare", "%", "gold_social_welfare", "Biến động tỷ lệ nghèo trong khung 5 năm.", ("poverty change 5 year", "poverty change", "biến động nghèo", "bien dong ngheo")),
    _indicator("urban_pop_pct", "Tỷ lệ dân số đô thị", "Urban Population Percentage", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ dân số sống ở khu vực đô thị.", ("urban population percentage", "urban population share", "tỷ lệ dân số đô thị", "ty le dan so do thi")),
    _indicator("urban_pop_growth", "Tăng trưởng dân số đô thị", "Urban Population Growth", "social_welfare", "%", "gold_social_welfare", "Tốc độ tăng dân số đô thị.", ("urban population growth", "urban growth", "tăng dân số đô thị", "tang dan so do thi")),
    _indicator("pop_density", "Mật độ dân số", "Population Density", "social_welfare", "people/km²", "gold_social_welfare", "Mật độ dân số, tính theo người trên km².", ("population density", "pop density", "mật độ dân số", "mat do dan so")),
    _indicator("log_pop_density", "Log mật độ dân số", "Log Population Density", "social_welfare", "log(people/km²)", "gold_social_welfare", "Logarit của mật độ dân số.", ("log population density", "log pop density", "log mật độ dân số", "log mat do dan so")),
    _indicator("pop_growth", "Tăng trưởng dân số", "Population Growth", "social_welfare", "%", "gold_social_welfare", "Tốc độ tăng dân số hằng năm.", ("population growth", "pop growth", "tăng dân số", "tang dan so")),
    _indicator("hcons_share", "Tỷ lệ tiêu dùng hộ gia đình", "Household Consumption Share", "social_welfare", "%", "gold_social_welfare", "Tỷ lệ tiêu dùng hộ gia đình trên GDP.", ("household consumption share", "household consumption", "tiêu dùng hộ gia đình", "tieu dung ho gia dinh")),
    _indicator("hcons_growth", "Tăng trưởng tiêu dùng hộ gia đình", "Household Consumption Growth", "social_welfare", "%", "gold_social_welfare", "Tốc độ tăng trưởng tiêu dùng hộ gia đình.", ("household consumption growth", "hcons growth", "tăng trưởng tiêu dùng hộ gia đình", "tang truong tieu dung ho gia dinh")),
    _indicator("trade_pct_gdp", "Thương mại/GDP", "Trade Percentage of GDP", "social_welfare", "%", "gold_social_welfare", "Tổng kim ngạch thương mại so với GDP, thường dùng để đo độ mở thương mại.", ("trade openness", "trade_openness", "trade-to-GDP", "trade to GDP", "trade percentage of GDP", "trade pct gdp", "trade/GDP", "trade_open_pct_gdp", "độ mở thương mại", "do mo thuong mai", "thương mại/GDP", "thuong mai/GDP", "thương mại trên GDP", "thuong mai tren GDP")),

    _indicator("decade", "Thập kỷ", "Decade", "structural_composition", "year", "gold_structural_composition", "Thập kỷ của quan sát trong bảng cơ cấu kinh tế.", ("decade indicator", "ten-year period", "thập kỷ", "thap ky")),
    _indicator("GDP_value", "Giá trị GDP", "GDP Value", "structural_composition", "current US$", "gold_structural_composition", "Giá trị GDP danh nghĩa theo USD hiện hành.", ("GDP current USD", "GDP value", "giá trị GDP", "gia tri GDP")),
    _indicator("GFCF_value", "Giá trị đầu tư tài sản cố định", "Gross Fixed Capital Formation Value", "structural_composition", "current US$", "gold_structural_composition", "Giá trị đầu tư tài sản cố định theo USD hiện hành.", ("GFCF value", "investment value", "giá trị đầu tư tài sản cố định", "gia tri dau tu tai san co dinh")),
    _indicator("GNI_value", "Giá trị GNI", "Gross National Income Value", "structural_composition", "current US$", "gold_structural_composition", "Giá trị tổng thu nhập quốc dân theo USD hiện hành.", ("GNI value", "national income value", "giá trị GNI", "gia tri GNI")),
    _indicator("Agri_VA", "Giá trị gia tăng nông nghiệp", "Agriculture Value Added", "structural_composition", "current US$", "gold_structural_composition", "Giá trị gia tăng nông nghiệp theo USD hiện hành.", ("agriculture value added", "agri value added", "giá trị gia tăng nông nghiệp", "gia tri gia tang nong nghiep")),
    _indicator("Manuf_VA", "Giá trị gia tăng chế biến chế tạo", "Manufacturing Value Added", "structural_composition", "current US$", "gold_structural_composition", "Giá trị gia tăng công nghiệp chế biến chế tạo theo USD hiện hành.", ("manufacturing value added", "manuf value added", "giá trị gia tăng công nghiệp chế biến", "gia tri gia tang cong nghiep che bien")),
    _indicator("VA_FoodBev", "Giá trị gia tăng thực phẩm và đồ uống", "Food and Beverage Value Added", "structural_composition", "current US$", "gold_structural_composition", "Giá trị gia tăng ngành thực phẩm và đồ uống theo USD hiện hành.", ("food beverage value added", "food and beverage value", "giá trị gia tăng thực phẩm đồ uống", "gia tri gia tang thuc pham do uong")),
    _indicator("GFCF_to_GDP", "Đầu tư tài sản cố định/GDP", "Gross Fixed Capital Formation to GDP", "structural_composition", "%", "gold_structural_composition", "Tỷ lệ đầu tư tài sản cố định trên GDP.", ("GFCF to GDP", "gross fixed capital formation to GDP", "investment to GDP", "đầu tư cố định gộp/GDP", "dau tu co dinh gop/GDP", "đầu tư tài sản cố định/GDP", "dau tu tai san co dinh/GDP")),
    _indicator("GNI_to_GDP", "GNI/GDP", "Gross National Income to GDP", "structural_composition", "ratio", "gold_structural_composition", "Tỷ lệ tổng thu nhập quốc dân trên GDP.", ("GNI to GDP", "GNI ratio", "tỷ lệ GNI trên GDP", "ty le GNI tren GDP")),
    _indicator("agri_va_share", "Tỷ trọng nông nghiệp", "Agriculture Value Added Share", "structural_composition", "%", "gold_structural_composition", "Tỷ trọng giá trị gia tăng nông nghiệp trong GDP.", ("agriculture share", "agri VA share", "tỷ trọng nông nghiệp", "ty trong nong nghiep")),
    _indicator("manuf_va_share", "Tỷ trọng chế biến chế tạo", "Manufacturing Value Added Share", "structural_composition", "%", "gold_structural_composition", "Tỷ trọng giá trị gia tăng công nghiệp chế biến chế tạo trong GDP.", ("manufacturing share", "manuf VA share", "tỷ trọng công nghiệp chế biến", "ty trong cong nghiep che bien")),
    _indicator("food_bev_share_manuf", "Tỷ trọng thực phẩm đồ uống trong chế biến", "Food and Beverage Share of Manufacturing", "structural_composition", "%", "gold_structural_composition", "Tỷ trọng ngành thực phẩm và đồ uống trong sản xuất chế biến.", ("food beverage manufacturing share", "food and beverage manufacturing", "thực phẩm đồ uống", "thuc pham do uong")),
    _indicator("flag_score", "Điểm cờ chất lượng dữ liệu", "Data Quality Flag", "quality", "0-3", "gold_structural_composition", "Điểm hoặc cờ chất lượng dữ liệu trong bảng gold.", ("flag score", "data quality flag", "điểm chất lượng dữ liệu", "diem chat luong du lieu")),
)


INDICATORS: dict[str, CanonicalIndicator] = {indicator.code: indicator for indicator in _INDICATOR_ROWS}


AMBIGUOUS_NORMALIZED_ALIASES: set[str] = {
    "gdp",
    "debt",
    "growth",
    "trade",
    "tax",
}


def normalize_catalog_text(text: str) -> str:
    normalized = text.lower().strip().replace("đ", "d")
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"[^a-z0-9%\s/.-]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def get_indicator(code: str) -> CanonicalIndicator | None:
    return INDICATORS.get(code)


def list_indicators() -> list[CanonicalIndicator]:
    return list(INDICATORS.values())


def list_indicator_codes() -> list[str]:
    return list(INDICATORS.keys())


def is_supported_indicator(code: str) -> bool:
    return code in INDICATORS


def get_indicator_by_column(gold_table: str, gold_column: str) -> CanonicalIndicator | None:
    for indicator in INDICATORS.values():
        if indicator.gold_table == gold_table and indicator.gold_column == gold_column:
            return indicator
    return None


def _contains_alias(normalized_text: str, normalized_alias: str) -> bool:
    if not normalized_alias or normalized_alias in AMBIGUOUS_NORMALIZED_ALIASES:
        return False

    if len(normalized_alias) <= 3:
        return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text) is not None

    if re.fullmatch(r"[a-z0-9]+", normalized_alias):
        return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text) is not None

    return normalized_alias in normalized_text


def _score_alias(normalized_text: str, alias: str) -> float:
    normalized_alias = normalize_catalog_text(alias)
    if normalized_text == normalized_alias:
        return 1.0
    if not _contains_alias(normalized_text, normalized_alias):
        return 0.0
    return min(0.99, 0.75 + len(normalized_alias) / 240)


def resolve_indicator_aliases(text: str, limit: int = 3) -> list[IndicatorAliasMatch]:
    if limit <= 0:
        return []

    normalized_text = normalize_catalog_text(text)
    matches: list[IndicatorAliasMatch] = []

    for indicator in INDICATORS.values():
        best_score = 0.0
        best_alias = ""
        best_alias_length = 0

        for alias in indicator.aliases:
            normalized_alias = normalize_catalog_text(alias)
            score = _score_alias(normalized_text, alias)
            alias_length = len(normalized_alias)
            if score > best_score or (score == best_score and alias_length > best_alias_length):
                best_score = score
                best_alias = alias
                best_alias_length = alias_length

        if best_score >= 0.75:
            matches.append(
                IndicatorAliasMatch(
                    indicator=indicator,
                    matched_alias=best_alias,
                    confidence=round(best_score, 3),
                )
            )

    matches.sort(
        key=lambda item: (
            item.confidence,
            len(normalize_catalog_text(item.matched_alias)),
        ),
        reverse=True,
    )
    return matches[:limit]


def resolve_indicator_alias(text: str) -> IndicatorAliasMatch | None:
    matches = resolve_indicator_aliases(text, limit=1)
    return matches[0] if matches else None


def get_analytics_columns(code: str) -> list[str]:
    if not indicator_has_analytics(code):
        return []
    return [f"{code}_{suffix}" for suffix in ANALYTICS_SUFFIXES]


def get_analytics_table_for_indicator(code: str) -> str | None:
    indicator = get_indicator(code)
    return indicator.analytics_table if indicator else None


def indicator_has_analytics(code: str) -> bool:
    return get_analytics_table_for_indicator(code) is not None


def indicator_supports_trend(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.supports_trend)


def indicator_supports_anomaly(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.supports_anomaly)


def indicator_used_for_cluster(code: str) -> bool:
    indicator = get_indicator(code)
    return bool(indicator and indicator.used_for_cluster)


def get_indicator_analytics_metadata(code: str) -> dict:
    analytics_table = get_analytics_table_for_indicator(code)
    return {
        "has_analytics": analytics_table is not None,
        "analytics_table": analytics_table,
        "analytics_columns": get_analytics_columns(code),
        "supports_trend": indicator_supports_trend(code),
        "supports_anomaly": indicator_supports_anomaly(code),
        "used_for_cluster": indicator_used_for_cluster(code),
    }


def get_supported_indicators_compact(max_aliases_per_indicator: int = 8) -> list[dict]:
    return [
        {
            "code": indicator.code,
            "name_vi": indicator.name_vi,
            "name_en": indicator.name_en,
            "unit": indicator.unit,
            "description_vi": indicator.description_vi,
            "aliases": list(indicator.aliases[:max_aliases_per_indicator]),
            "supports_trend": indicator.supports_trend,
            "supports_anomaly": indicator.supports_anomaly,
        }
        for indicator in INDICATORS.values()
    ]
