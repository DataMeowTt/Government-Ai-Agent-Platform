from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorMeta:
    code: str
    name: str
    category: str
    unit: str
    gold_table: str
    analytics_table: str | None = None
    description: str = ""
    aliases: tuple[str, ...] = ()


_INDICATOR_ROWS = (
    ("rGDP_growth_YoY", "Real GDP Growth Year-over-Year", "growth_dynamics", "%", "gold_growth_dynamics", "analytics_gold_growth_dynamics", "Tốc độ tăng trưởng GDP thực so với cùng kỳ năm trước.", ("real GDP growth", "real GDP growth YoY", "tăng trưởng GDP thực", "tang truong GDP thuc")),
    ("rolling_mean_5yr", "5-Year Rolling Mean Growth", "growth_dynamics", "%", "gold_growth_dynamics", "analytics_gold_growth_dynamics", "Trung bình trượt 5 năm của tăng trưởng GDP.", ("rolling mean 5 year", "5-year growth average", "trung bình trượt 5 năm", "trung binh truot 5 nam")),
    ("trend_deviation", "Trend Deviation", "growth_dynamics", "%", "gold_growth_dynamics", "analytics_gold_growth_dynamics", "Độ lệch của tăng trưởng thực tế so với xu hướng dài hạn.", ("trend deviation", "deviation from trend", "độ lệch xu hướng", "do lech xu huong")),
    ("GDP_growth_YoY", "Nominal GDP Growth Year-over-Year", "growth_dynamics", "%", "gold_growth_dynamics", "analytics_gold_growth_dynamics", "Tốc độ tăng trưởng GDP danh nghĩa so với năm trước.", ("nominal GDP growth", "GDP growth YoY", "tăng trưởng GDP danh nghĩa", "tang truong GDP danh nghia")),
    ("GDP_pc_growth_gap", "GDP per Capita Growth Gap", "growth_dynamics", "%", "gold_growth_dynamics", "analytics_gold_growth_dynamics", "Chênh lệch giữa tăng trưởng GDP tổng và tăng trưởng GDP bình quân đầu người.", ("GDP per capita growth gap", "GDP pc growth gap", "chênh lệch GDP bình quân", "chenh lech GDP binh quan")),
    ("GDP_growth_trend_5yr", "GDP Growth Trend 5-year", "growth_dynamics", "%", "gold_growth_dynamics", None, "Xu hướng tăng trưởng GDP trong khung 5 năm.", ("GDP growth trend 5 year", "GDP trend", "xu hướng GDP 5 năm", "xu huong GDP 5 nam")),
    ("log_rGDP_pc_USD", "Log Real GDP per Capita USD", "growth_dynamics", "log(USD)", "gold_growth_dynamics", None, "Logarit GDP thực bình quân đầu người tính bằng USD.", ("log real GDP per capita", "log rGDP per capita", "GDP per capita", "GDP bình quân đầu người", "GDP đầu người", "GDP binh quan dau nguoi", "GDP dau nguoi", "thu nhập bình quân", "thu nhap binh quan", "income per capita", "log GDP thực bình quân", "log GDP thuc binh quan")),

    ("agri_va_share", "Agriculture Value Added Share", "structural_composition", "%", "gold_structural_composition", "analytics_gold_structural_composition", "Tỷ trọng giá trị gia tăng nông nghiệp trong GDP.", ("agriculture share", "agri VA share", "tỷ trọng nông nghiệp", "ty trong nong nghiep")),
    ("manuf_va_share", "Manufacturing Value Added Share", "structural_composition", "%", "gold_structural_composition", "analytics_gold_structural_composition", "Tỷ trọng giá trị gia tăng công nghiệp chế biến trong GDP.", ("manufacturing share", "manuf VA share", "tỷ trọng công nghiệp chế biến", "ty trong cong nghiep che bien")),
    ("food_bev_share_manuf", "Food and Beverage Share of Manufacturing", "structural_composition", "%", "gold_structural_composition", "analytics_gold_structural_composition", "Tỷ trọng ngành thực phẩm và đồ uống trong sản xuất chế biến.", ("food beverage manufacturing share", "food and beverage manufacturing", "thực phẩm đồ uống", "thuc pham do uong")),
    ("GFCF_to_GDP", "Gross Fixed Capital Formation to GDP", "structural_composition", "%", "gold_structural_composition", "analytics_gold_structural_composition", "Tỷ lệ đầu tư tài sản cố định trên GDP.", ("GFCF to GDP", "gross fixed capital formation to GDP", "investment to GDP", "đầu tư cố định gộp/GDP", "dau tu co dinh gop/GDP", "đầu tư tài sản cố định/GDP", "dau tu tai san co dinh/GDP", "đầu tư tài sản cố định trên GDP", "dau tu tai san co dinh tren GDP")),
    ("GNI_to_GDP", "Gross National Income to GDP", "structural_composition", "ratio", "gold_structural_composition", "analytics_gold_structural_composition", "Tỷ lệ tổng thu nhập quốc dân trên GDP.", ("GNI to GDP", "GNI ratio", "tỷ lệ GNI trên GDP", "ty le GNI tren GDP")),
    ("decade", "Decade", "structural_composition", "year", "gold_structural_composition", None, "Thập kỷ của quan sát trong bảng structural composition.", ("decade indicator", "ten-year period", "thập kỷ", "thap ky")),
    ("GDP_value", "GDP Value", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị GDP danh nghĩa theo USD hiện hành trong bảng structural composition.", ("GDP current USD", "GDP value", "giá trị GDP", "gia tri GDP")),
    ("GFCF_value", "Gross Fixed Capital Formation Value", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị đầu tư tài sản cố định theo USD hiện hành.", ("GFCF value", "investment value", "giá trị đầu tư tài sản cố định", "gia tri dau tu tai san co dinh")),
    ("GNI_value", "Gross National Income Value", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị tổng thu nhập quốc dân theo USD hiện hành.", ("GNI value", "national income value", "giá trị GNI", "gia tri GNI")),
    ("Agri_VA", "Agriculture Value Added", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị gia tăng nông nghiệp theo USD hiện hành.", ("agriculture value added", "agri value added", "giá trị gia tăng nông nghiệp", "gia tri gia tang nong nghiep")),
    ("Manuf_VA", "Manufacturing Value Added", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị gia tăng công nghiệp chế biến theo USD hiện hành.", ("manufacturing value added", "manuf value added", "giá trị gia tăng công nghiệp chế biến", "gia tri gia tang cong nghiep che bien")),
    ("VA_FoodBev", "Food and Beverage Value Added", "structural_composition", "current US$", "gold_structural_composition", None, "Giá trị gia tăng ngành thực phẩm và đồ uống theo USD hiện hành.", ("food beverage value added", "food and beverage value", "giá trị gia tăng thực phẩm đồ uống", "gia tri gia tang thuc pham do uong")),
    ("flag_score", "Data Quality Flag", "quality", "0-3", "gold_structural_composition", None, "Điểm hoặc cờ chất lượng dữ liệu trong bảng gold.", ("flag score", "data quality flag", "điểm chất lượng dữ liệu", "diem chat luong du lieu")),

    ("govdebt_GDP", "Government Debt / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Tỷ lệ nợ công trên GDP, thường dùng để theo dõi rủi ro tài khóa.", ("government debt", "public debt", "debt-to-GDP", "debt to GDP", "government debt/GDP", "public debt/GDP", "nợ công", "no cong", "nợ công/GDP", "no cong/GDP")),
    ("debt_change_YoY", "Debt Change Year-over-Year", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Biến động nợ công so với năm trước.", ("debt change YoY", "debt change", "biến động nợ công", "bien dong no cong")),
    ("govrev_GDP", "Government Revenue / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Tỷ lệ thu ngân sách chính phủ trên GDP.", ("government revenue", "revenue-to-GDP", "thu ngân sách", "thu ngan sach")),
    ("govexp_GDP", "Government Expenditure / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Tỷ lệ chi tiêu chính phủ trên GDP.", ("government expenditure", "expenditure-to-GDP", "chi ngân sách", "chi ngan sach")),
    ("fiscal_balance_GDP", "Fiscal Balance / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Cân đối ngân sách trên GDP, giá trị âm thường biểu thị thâm hụt.", ("fiscal balance", "fiscal balance/GDP", "budget balance", "budget balance/GDP", "cân đối ngân sách", "can doi ngan sach", "cán cân ngân sách/GDP", "can can ngan sach/GDP")),
    ("cumulative_deficit_5yr", "Cumulative Deficit 5-year", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Tổng thâm hụt tích lũy trong giai đoạn 5 năm.", ("cumulative deficit 5 year", "cumulative deficit", "thâm hụt tích lũy", "tham hut tich luy")),
    ("ltrate", "Long-term Interest Rate", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Lãi suất dài hạn.", ("long-term interest rate", "long-term rate", "lãi suất dài hạn", "lai suat dai han")),
    ("infl", "Inflation GDP Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Lạm phát đo bằng GDP deflator trong bảng fiscal monetary.", ("GDP deflator inflation rate", "infl rate", "lạm phát deflator", "lam phat deflator")),
    ("real_interest_rate", "Real Interest Rate", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Lãi suất thực sau khi điều chỉnh lạm phát.", ("real interest rate", "real rate", "lãi suất thực", "lai suat thuc")),
    ("tax_revenue_pct_GDP", "Tax Revenue / GDP", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Tỷ lệ thu thuế trên GDP.", ("tax revenue", "tax-to-GDP", "thu thuế", "thu thue")),
    ("inflation_cpi", "Inflation CPI", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Lạm phát theo chỉ số giá tiêu dùng CPI.", ("CPI inflation", "consumer price inflation", "lạm phát CPI", "lam phat CPI", "inflation CPI")),
    ("inflation_deflator", "Inflation Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Lạm phát theo GDP deflator, raw-only trong bảng fiscal monetary.", ("GDP deflator", "deflator inflation", "lạm phát theo deflator", "lam phat theo deflator")),
    ("inflation_gap", "Inflation Gap CPI minus Deflator", "fiscal_monetary", "%", "gold_fiscal_monetary", "analytics_gold_fiscal_monetary", "Chênh lệch giữa lạm phát CPI và lạm phát theo GDP deflator.", ("inflation gap", "CPI deflator gap", "chênh lệch lạm phát", "chenh lech lam phat")),
    ("rolling_3yr_avg_cpi", "3-Year Average CPI Inflation", "fiscal_monetary", "%", "gold_fiscal_monetary", None, "Trung bình trượt 3 năm của lạm phát CPI.", ("3-year average CPI inflation", "rolling 3-year CPI", "trung bình CPI 3 năm", "trung binh CPI 3 nam")),

    ("SovDebtCrisis", "Sovereign Debt Crisis", "crisis_risk", "0/1", "gold_crisis_risk", None, "Biến nhị phân cho biết có khủng hoảng nợ công trong năm hay không.", ("sovereign debt crisis", "debt crisis", "khủng hoảng nợ công", "khung hoang no cong")),
    ("CurrencyCrisis", "Currency Crisis", "crisis_risk", "0/1", "gold_crisis_risk", None, "Biến nhị phân cho biết có khủng hoảng tiền tệ trong năm hay không.", ("currency crisis", "exchange rate crisis", "khủng hoảng tiền tệ", "khung hoang tien te")),
    ("BankingCrisis", "Banking Crisis", "crisis_risk", "0/1", "gold_crisis_risk", None, "Biến nhị phân cho biết có khủng hoảng ngân hàng trong năm hay không.", ("banking crisis", "bank crisis", "khủng hoảng ngân hàng", "khung hoang ngan hang")),
    ("crisis_composite", "Crisis Composite Index", "crisis_risk", "0-3", "gold_crisis_risk", None, "Chỉ số tổng hợp số loại khủng hoảng xảy ra trong một năm.", ("crisis composite", "crisis index", "chỉ số khủng hoảng tổng hợp", "chi so khung hoang tong hop")),
    ("crisis_any", "Any Crisis Occurred", "crisis_risk", "0/1", "gold_crisis_risk", None, "Biến nhị phân cho biết có ít nhất một loại khủng hoảng trong năm.", ("any crisis", "crisis occurred", "có khủng hoảng", "co khung hoang")),
    ("REER_deviation", "REER Deviation", "crisis_risk", "%", "gold_crisis_risk", "analytics_gold_crisis_risk", "Độ lệch tỷ giá hiệu dụng thực so với xu hướng hoặc mức tham chiếu.", ("REER deviation", "real effective exchange rate deviation", "độ lệch REER", "do lech REER")),
    ("spending_efficiency", "Spending Efficiency", "crisis_risk", "ratio", "gold_crisis_risk", "analytics_gold_crisis_risk", "Thước đo hiệu quả chi tiêu công.", ("spending efficiency", "public spending efficiency", "hiệu quả chi tiêu", "hieu qua chi tieu")),

    ("unemployment_total", "Unemployment Rate Total", "social_welfare", "%", "gold_social_welfare", "analytics_gold_social_welfare", "Tỷ lệ thất nghiệp của toàn bộ lực lượng lao động.", ("unemployment", "unemployment rate", "total unemployment", "thất nghiệp", "that nghiep")),
    ("unemployment_youth", "Youth Unemployment Rate", "social_welfare", "%", "gold_social_welfare", None, "Tỷ lệ thất nghiệp trong nhóm lao động trẻ.", ("youth unemployment", "youth unemployment rate", "thất nghiệp thanh niên", "that nghiep thanh nien")),
    ("youth_unemployment_gap", "Youth Unemployment Gap", "social_welfare", "%", "gold_social_welfare", "analytics_gold_social_welfare", "Chênh lệch giữa thất nghiệp thanh niên và thất nghiệp tổng thể.", ("youth unemployment gap", "youth jobless gap", "chênh lệch thất nghiệp thanh niên", "chenh lech that nghiep thanh nien")),
    ("youth_gap_ratio", "Youth Gap Ratio", "social_welfare", "ratio", "gold_social_welfare", None, "Tỷ lệ thất nghiệp thanh niên so với thất nghiệp tổng thể.", ("youth gap ratio", "youth unemployment ratio", "tỷ lệ thất nghiệp thanh niên trên tổng thể", "ty le that nghiep thanh nien tren tong the")),
    ("self_employed_pct", "Self-Employed Percentage", "social_welfare", "%", "gold_social_welfare", None, "Tỷ lệ lao động tự doanh trong tổng việc làm.", ("self-employed", "self-employed percentage", "lao động tự doanh", "lao dong tu doanh")),
    ("poverty_headcount", "Poverty Headcount Ratio", "social_welfare", "%", "gold_social_welfare", "analytics_gold_social_welfare", "Tỷ lệ dân số sống dưới ngưỡng nghèo.", ("poverty headcount", "poverty rate", "tỷ lệ nghèo", "ty le ngheo")),
    ("poverty_change_5yr", "Poverty Change 5-year", "social_welfare", "%", "gold_social_welfare", "analytics_gold_social_welfare", "Biến động tỷ lệ nghèo trong khung 5 năm.", ("poverty change 5 year", "poverty change", "biến động nghèo", "bien dong ngheo")),
    ("urban_pop_pct", "Urban Population Percentage", "social_welfare", "%", "gold_social_welfare", None, "Tỷ lệ dân số sống ở khu vực đô thị.", ("urban population percentage", "urban population share", "tỷ lệ dân số đô thị", "ty le dan so do thi")),
    ("urban_pop_growth", "Urban Population Growth", "social_welfare", "%", "gold_social_welfare", None, "Tốc độ tăng dân số đô thị.", ("urban population growth", "urban growth", "tăng dân số đô thị", "tang dan so do thi")),
    ("pop_density", "Population Density", "social_welfare", "people/km²", "gold_social_welfare", None, "Mật độ dân số, tính theo người trên km².", ("population density", "pop density", "mật độ dân số", "mat do dan so")),
    ("log_pop_density", "Log Population Density", "social_welfare", "log(people/km²)", "gold_social_welfare", None, "Logarit của mật độ dân số.", ("log population density", "log pop density", "log mật độ dân số", "log mat do dan so")),
    ("pop_growth", "Population Growth", "social_welfare", "%", "gold_social_welfare", None, "Tốc độ tăng dân số hằng năm.", ("population growth", "pop growth", "tăng dân số", "tang dan so")),
    ("hcons_share", "Household Consumption Share", "social_welfare", "%", "gold_social_welfare", None, "Tỷ lệ tiêu dùng hộ gia đình trên GDP.", ("household consumption share", "household consumption", "tiêu dùng hộ gia đình", "tieu dung ho gia dinh")),
    ("hcons_growth", "Household Consumption Growth", "social_welfare", "%", "gold_social_welfare", "analytics_gold_social_welfare", "Tốc độ tăng trưởng tiêu dùng hộ gia đình.", ("household consumption growth", "hcons growth", "tăng trưởng tiêu dùng hộ gia đình", "tang truong tieu dung ho gia dinh")),
    ("trade_pct_gdp", "Trade Percentage of GDP", "social_welfare", "%", "gold_social_welfare", None, "Tổng thương mại so với GDP.", ("trade percentage of GDP", "trade-to-GDP", "trade to GDP", "trade openness", "độ mở thương mại", "do mo thuong mai", "thương mại/GDP", "thuong mai/GDP", "thương mại trên GDP", "thuong mai tren GDP")),
)


INDICATORS: dict[str, IndicatorMeta] = {
    code: IndicatorMeta(
        code=code,
        name=name,
        category=category,
        unit=unit,
        gold_table=gold_table,
        analytics_table=analytics_table,
        description=description,
        aliases=aliases,
    )
    for (
        code,
        name,
        category,
        unit,
        gold_table,
        analytics_table,
        description,
        aliases,
    ) in _INDICATOR_ROWS
}


def get_indicator(code: str) -> IndicatorMeta | None:
    return INDICATORS.get(code)


def list_indicators() -> list[IndicatorMeta]:
    return list(INDICATORS.values())


def list_indicator_codes() -> list[str]:
    return list(INDICATORS.keys())
