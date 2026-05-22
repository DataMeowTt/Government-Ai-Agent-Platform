
# Danh Sách Chỉ Số Dữ Liệu - Government AI Agent Platform



## TỔNG QUAN KIẾN TRÚC DỮ LIỆU

```
Silver Layer (long format)
        ↓
Gold Layer (5 bảng wide format) → Analytics Layer (trend + anomaly + cluster)
        ↓
Server API (NestJS) → Frontend/AI Agent
```

---

## 1. BẢNG: gold_growth_dynamics
*Mục đích: Phân tích động thái tăng trưởng kinh tế, phục vụ forecasting và phát hiện chu kỳ kinh tế*

| Chỉ số | Tên đầy đủ | Ý nghĩa | Đơn vị | Ví dụ minh họa |
|--------|-----------|---------|--------|---------------|
| `rGDP_growth_YoY` | Real GDP Growth (Year-over-Year) | Tốc độ tăng trưởng GDP thực tế so với cùng kỳ năm trước, đã điều chỉnh lạm phát | % | VNM 2020: 2.9% (tăng trưởng dương dù có COVID) |
| `rolling_mean_5yr` | 5-Year Rolling Mean Growth | Trung bình trượt 5 năm của tăng trưởng GDP, giúp làm mịn nhiễu ngắn hạn | % | VNM 2018-2022: ~6.2% (xu hướng ổn định) |
| `trend_deviation` | Trend Deviation | Độ lệch của tăng trưởng thực tế so với xu hướng dài hạn, phát hiện "điểm gãy" cấu trúc | % | ARG 2001: -15% (khủng hoảng nợ) |
| `GDP_growth_YoY` | Nominal GDP Growth (YoY) | Tăng trưởng GDP danh nghĩa, chưa điều chỉnh lạm phát | % | TUR 2022: 78% (lạm phát cao làm tăng GDP danh nghĩa) |
| `GDP_pc_growth_gap` | GDP per Capita Growth Gap | Chênh lệch giữa tăng trưởng GDP tổng và GDP bình quân, phản ánh tác động dân số | % | IND: gap âm nhẹ (dân số tăng nhanh) |
| `GDP_growth_trend_5yr` | GDP Growth Trend (5-year) | Trung bình trượt 5 năm của tăng trưởng GDP, dùng làm baseline so sánh xu hướng ngắn hạn. | % | CHN 2015-2019: trend ~6.5%/năm |
| `log_rGDP_pc_USD` | Log Real GDP per Capita (USD) | Logarit của GDP thực tế bình quân đầu người (USD), dùng cho mô hình hồi quy (Sử dụng công thức log1p để xử lý giá trị ≤ 0) | log(USD) | USA: ~10.5; ETH: ~6.2 |

🔹 **Analytics phái sinh** (`analytics_gold_growth_dynamics`):
| Cột Analytics | Mô tả |
|--------------|-------|
| `{indicator}_trend` | Giá trị xu hướng từ hồi quy tuyến tính |
| `{indicator}_residual` | Phần dư = Actual - Trend, dùng phát hiện bất thường |
| `{indicator}_anomaly_score` | Điểm bất thường [0-1] từ Isolation Forest, >0.75 = cảnh báo |

---

## 2. BẢNG: gold_structural_composition
*Mục đích: Phân tích cấu trúc kinh tế, chuyển dịch ngành, phục vụ phân loại giai đoạn phát triển*

| Chỉ số | Tên đầy đủ | Ý nghĩa | Đơn vị | Ví dụ minh họa |
|--------|-----------|---------|--------|---------------|
| `agri_va_share` | Agriculture Value Added Share | Tỷ trọng giá trị gia tăng nông nghiệp trong GDP | % | ETH: ~40% (nền kinh tế nông nghiệp) |
| `manuf_va_share` | Manufacturing Value Added Share | Tỷ trọng giá trị gia tăng công nghiệp chế biến trong GDP | % | KOR: ~28% (công nghiệp hóa) |
| `food_bev_share_manuf` | Food & Beverage Share of Manufacturing | Tỷ trọng ngành thực phẩm-đồ uống trong tổng giá trị gia tăng công nghiệp | % | VNM: ~15% (đa dạng hóa công nghiệp) |
| `GFCF_to_GDP` | Gross Fixed Capital Formation / GDP | Tỷ lệ đầu tư tài sản cố định/GDP, chỉ báo cường độ đầu tư | % | CHN: ~43% (đầu tư cao) |
| `GNI_to_GDP` | Gross National Income / GDP | Tỷ lệ GNI/GDP, phản ánh phụ thuộc vào dòng vốn nước ngoài | ratio | IRL: >1.2 (nhiều FDI inflow) |
| `GDP_growth_YoY` | GDP Growth (YoY) | Tăng trưởng GDP, dùng làm biến mục tiêu trong phân tích cấu trúc | % | — |
| `flag_score` | Data Quality Flag | Điểm chất lượng dữ liệu (0=đầy đủ, 3=thiếu nhiều) | 0-3 | — |
| `decade` | Decade | Thập kỷ (1990, 2000, 2010...), dùng phân tích theo giai đoạn | year | — |

🔹 **Analytics phái sinh** (`analytics_gold_structural_composition`):
| Cột Analytics | Mô tả |
|--------------|-------|
| `{indicator}_trend` | Xu hướng dài hạn của chỉ số cấu trúc |
| `{indicator}_anomaly_score` | Điểm bất thường, ví dụ: `agri_va_share_anomaly_score > 0.8` = chuyển dịch đột ngột |

---

## 3. BẢNG: gold_fiscal_monetary
*Mục đích: Đánh giá bền vững tài khóa, chính sách tiền tệ, cảnh báo rủi ro nợ công*

| Chỉ số | Tên đầy đủ | Ý nghĩa | Đơn vị | Ví dụ minh họa |
|--------|-----------|---------|--------|---------------|
| `govdebt_GDP` | Government Debt / GDP | Tỷ lệ nợ công/GDP, ngưỡng cảnh báo thường >90% | % | GRC 2010: 146% (khủng hoảng nợ) |
| `debt_change_YoY` | Debt Change (YoY) | Biến động nợ công so với năm trước, chỉ báo sớm rủi ro | % | ITA 2020: +15% (COVID stimulus) |
| `govrev_GDP` | Government Revenue / GDP | Tỷ lệ thu ngân sách/GDP, phản ánh năng lực huy động | % | DNK: ~45% (nhà nước phúc lợi) |
| `govexp_GDP` | Government Expenditure / GDP | Tỷ lệ chi ngân sách/GDP | % | FRA: ~58% |
| `fiscal_balance_GDP` | Fiscal Balance / GDP | Cân đối ngân sách/GDP, âm = thâm hụt | % | USA 2020: -15% (deficit lớn) |
| `cumulative_deficit_5yr` | Cumulative Deficit (5-year) | Tổng thâm hụt tích lũy 5 năm, cảnh báo áp lực nợ | % | — |
| `ltrate` | Long-term Interest Rate | Lãi suất dài hạn (trái phiếu chính phủ 10 năm) | % | DEU 2022: ~2.5% |
| `infl` | Inflation Rate (GDP Deflator) | Lạm phát tính bằng deflator GDP | % | TUR 2022: ~72% |
| `real_interest_rate` | Real Interest Rate | Lãi suất thực = nominal rate - inflation | % | Nếu infl=10%, ltrate=5% → real=-5% |
| `tax_revenue_pct_GDP` | Tax Revenue / GDP | Tỷ lệ thu thuế/GDP, chỉ báo hiệu quả thu ngân sách | % | SWE: ~40% |
| `inflation_cpi` | Inflation (CPI) | Lạm phát theo chỉ số giá tiêu dùng | % | — |
| `inflation_gap` | Inflation Gap (CPI - Deflator) | Chênh lệch lạm phát CPI và GDP deflator, phản ánh biến động giá nhập khẩu | % | Gap lớn = áp lực giá nhập khẩu |
| `rolling_3yr_avg_cpi` | 3-Year Avg CPI Inflation | Trung bình trượt 3 năm của lạm phát CPI | % | — |

🔹 **Analytics phái sinh** (`analytics_gold_fiscal_monetary`):
| Cột Analytics | Mô tả |
|--------------|-------|
| `govdebt_GDP_anomaly_score` | Điểm bất thường nợ công, >0.75 = cảnh báo rủi ro nợ |
| `fiscal_balance_GDP_residual` | Phần dư cân đối ngân sách, giá trị âm lớn = thâm hụt bất thường |

---

## 4. BẢNG: gold_crisis_risk
*Mục đích: Nhận diện sự kiện khủng hoảng, xây dựng hệ thống cảnh báo sớm*

| Chỉ số | Tên đầy đủ | Ý nghĩa | Đơn vị | Ví dụ minh họa |
|--------|-----------|---------|--------|---------------|
| `SovDebtCrisis` | Sovereign Debt Crisis | Biến nhị phân: 1 = có khủng hoảng nợ công trong năm | 0/1 | ARG 2001: 1 |
| `CurrencyCrisis` | Currency Crisis | Biến nhị phân: 1 = có khủng hoảng tiền tệ | 0/1 | THA 1997: 1 (khủng hoảng châu Á) |
| `BankingCrisis` | Banking Crisis | Biến nhị phân: 1 = có khủng hoảng ngân hàng | 0/1 | USA 2008: 1 |
| `crisis_composite` | Crisis Composite Index | Tổng số loại khủng hoảng xảy ra (0-3) | 0-3 | ARG 2001: 3 (nợ + tiền tệ + ngân hàng) |
| `crisis_any` | Any Crisis Occurred | Biến nhị phân: 1 = có ít nhất 1 loại khủng hoảng | 0/1 | — |
| `REER_deviation` | REER Deviation (%) | Độ lệch tỷ giá hiệu dụng thực so với trung bình 5 năm, chỉ báo sớm mất cân bằng | % | Giá trị < -20% = đồng nội tệ định giá thấp bất thường |
| `spending_efficiency` | Spending Efficiency | Tỷ lệ tăng trưởng GDP / chi tiêu chính phủ, đo hiệu quả chi tiêu công | ratio | Giá trị cao = chi tiêu hiệu quả |
| `govdebt_GDP` | Government Debt / GDP | (Thừa kế từ fiscal) Dùng làm biến đầu vào mô hình dự báo khủng hoảng | % | — |
| `fiscal_balance_GDP` | Fiscal Balance / GDP | (Thừa kế) Thâm hụt lớn thường đi trước khủng hoảng | % | — |
| `rGDP_growth_YoY` | Real GDP Growth | (Thừa kế) Suy thoái thường đi kèm khủng hoảng | % | — |

🔹 **Analytics phái sinh** (`analytics_gold_crisis_risk`):
| Cột Analytics | Mô tả |
|--------------|-------|
| `REER_deviation_anomaly_score` | Điểm bất thường tỷ giá, cảnh báo rủi ro tiền tệ |
| `spending_efficiency_residual` | Phần dư hiệu quả chi tiêu, giá trị thấp = chi tiêu kém hiệu quả |

---

## 5. BẢNG: gold_social_welfare
*Mục đích: Phân tích phúc lợi xã hội, bất bình đẳng, di cư đô thị*

| Chỉ số | Tên đầy đủ | Ý nghĩa | Đơn vị | Ví dụ minh họa |
|--------|-----------|---------|--------|---------------|
| `unemployment_total` | Unemployment Rate (Total) | Tỷ lệ thất nghiệp toàn bộ lực lượng lao động | % | ESP 2013: ~26% (hậu khủng hoảng) |
| `unemployment_youth` | Youth Unemployment Rate | Tỷ lệ thất nghiệp nhóm 15-24 tuổi | % | GRC 2013: ~58% |
| `youth_unemployment_gap` | Youth Unemployment Gap | Chênh lệch thất nghiệp thanh niên - tổng thể | % | Gap >10% = rủi ro bất ổn xã hội |
| `youth_gap_ratio` | Youth Gap Ratio | Tỷ lệ thất nghiệp thanh niên / tổng thể | ratio | Ratio >2.0 = thanh niên chịu tác động gấp đôi |
| `self_employed_pct` | Self-Employed (% of employment) | Tỷ lệ lao động tự doanh, chỉ báo khu vực phi chính thức | % | IND: ~80% (kinh tế phi chính thức lớn) |
| `poverty_headcount` | Poverty Headcount Ratio | Tỷ lệ dân số sống dưới ngưỡng nghèo quốc tế ($3.00/ngày) | % | NGA 2019: ~40% |
| `poverty_change_5yr` | Poverty Change (5-year) | Biến động tỷ lệ nghèo trong 5 năm, âm = giảm nghèo | % | CHN 2010-2015: -15% |
| `urban_pop_pct` | Urban Population (%) | Tỷ lệ dân số sống ở đô thị | % | BRA: ~87% |
| `urban_pop_growth` | Urban Population Growth | Tốc độ tăng dân số đô thị hàng năm | % | ETH: ~4.5%/năm (đô thị hóa nhanh) |
| `pop_density` | Population Density | Mật độ dân số (người/km²) | people/km² | BGD: ~1,100; AUS: ~3 |
| `log_pop_density` | Log Population Density | Logarit mật độ dân số, dùng cho mô hình hồi quy | log(people/km²) | — |
| `pop_growth` | Population Growth (annual) | Tốc độ tăng dân số tự nhiên | % | NIG: ~2.6%/năm |
| `hcons_share` | Household Consumption Share | Tỷ lệ tiêu dùng hộ gia đình/GDP | % | USA: ~68% |
| `hcons_growth` | Household Consumption Growth | Tăng trưởng tiêu dùng hộ gia đình | % | — |
| `trade_pct_gdp` | Trade (% of GDP) | Tổng kim ngạch xuất nhập khẩu/GDP, chỉ báo độ mở kinh tế | % | SGP: ~300% (nền kinh tế mở) |

🔹 **Analytics phái sinh** (`analytics_gold_social_welfare`):
| Cột Analytics | Mô tả |
|--------------|-------|
| `poverty_headcount_anomaly_score` | Điểm bất thường tỷ lệ nghèo, phát hiện thay đổi đột ngột |
| `unemployment_total_residual` | Phần dư thất nghiệp, giá trị dương lớn = thất nghiệp cao hơn xu hướng |

---

## 6. BẢNG: analytics_clusters
*Mục đích: Phân nhóm quốc gia theo đặc điểm cấu trúc, phục vụ phân tích so sánh*

| Cột | Ý nghĩa | Giá trị mẫu |
|-----|---------|-------------|
| `country_code` | Mã quốc gia ISO-3 | VNM, USA, ETH |
| `year` | Năm quan sát | 2020 |
| `cluster_id` | ID nhóm từ thuật toán K-Means (5 cụm) | 0, 1, 2, 3, 4 |
| `method` | Phương pháp phân cụm | "kmeans" |

**Ví dụ minh họa (Labels này có thể đảo ngược tùy năm chạy, cần kiểm tra centroid để gán nhãn thực tế)**:
| Cluster | Đặc điểm điển hình | Quốc gia mẫu |
|---------|-------------------|--------------|
| 0 | Nông nghiệp chủ đạo, thu nhập thấp | ETH, NER, TCD |
| 1 | Công nghiệp hóa nhanh, thu nhập trung bình | VNM, IDN, PHL |
| 2 | Dịch vụ chiếm ưu thế, thu nhập cao | USA, DEU, KOR |
| 3 | Phụ thuộc tài nguyên, biến động cao | NGA, AGO, VEN |
| 4 | Kinh tế nhỏ, mở, chuyên môn hóa | SGP, LUX, MLT |

---

## 7. QUY TRÌNH PHÁI SINH ANALYTICS TỪ GOLD

```
Gold Table (raw values)
        ↓
[trend.py] → Hồi quy tuyến tính theo country_code
        ↓
→ Tính: {indicator}_trend, {indicator}_residual, {indicator}_slope, {indicator}_r2
        ↓
[anomaly.py] → Isolation Forest trên residuals
        ↓
→ Tính: {indicator}_anomaly_score [0-1]
        ↓
[cluster.py] → K-Means trên structural indicators
        ↓
→ Gán: cluster_id cho từng (country_code, year)
```

**Cột Analytics chỉ được sinh cho các chỉ số khai báo trong TABLES_INDICATORS (analytic.txt). Các chỉ số khác giữ nguyên giá trị raw.**

---

## 8. DANH SÁCH CHỈ SỐ THEO NHÓM CHỦ ĐỀ (Dễ tra cứu)

### Tăng trưởng & Kinh tế vĩ mô
```
• rGDP_growth_YoY        → Tăng trưởng GDP thực
• rolling_mean_5yr       → Xu hướng tăng trưởng ổn định
• trend_deviation        → Phát hiện điểm gãy cấu trúc
• GDP_pc_growth_gap      → Tác động dân số lên tăng trưởng
```

### Tài khóa & Tiền tệ
```
• govdebt_GDP            → Rủi ro nợ công
• fiscal_balance_GDP     → Cân đối ngân sách
• real_interest_rate     → Chi phí vốn thực
• inflation_gap          → Áp lực giá nhập khẩu
```

### Rủi ro & Khủng hoảng
```
• crisis_composite       → Mức độ nghiêm trọng khủng hoảng
• REER_deviation         → Cảnh báo sớm mất cân bằng tỷ giá
• spending_efficiency    → Hiệu quả chi tiêu công
```

### Phúc lợi & Xã hội
```
• poverty_headcount      → Tỷ lệ nghèo
• youth_unemployment_gap → Rủi ro bất ổn thanh niên
• urban_pop_growth       → Tốc độ đô thị hóa
```

### Cấu trúc kinh tế
```
• agri_va_share          → Giai đoạn nông nghiệp
• manuf_va_share         → Công nghiệp hóa
• GFCF_to_GDP            → Cường độ đầu tư
```

---

> **Lưu ý**: 
> - Tất cả chỉ số có `_anomaly_score` ≥ 0.75 nên được xem xét cảnh báo
> - Chỉ số dạng flag (`SovDebtCrisis`, `crisis_any`) dùng cho classification
> - Chỉ số dạng ratio/percentage cần chuẩn hóa trước khi đưa vào mô hình ML
