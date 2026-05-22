import re
from dataclasses import asdict, dataclass

from app.resolver.indicator_resolver import normalize_text


@dataclass(frozen=True)
class CountryMeta:
    code: str
    name: str
    aliases: tuple[str, ...] = ()


def _country(code: str, name: str, *aliases: str) -> CountryMeta:
    deduped_aliases: list[str] = []
    for alias in (code, name, *aliases):
        if alias and alias not in deduped_aliases:
            deduped_aliases.append(alias)
    return CountryMeta(code, name, tuple(deduped_aliases))


COUNTRIES: dict[str, CountryMeta] = {
    "AFG": _country("AFG", "Afghanistan"),
    "DZA": _country("DZA", "Algeria"),
    "AGO": _country("AGO", "Angola"),
    "ARG": _country("ARG", "Argentina"),
    "AUS": _country("AUS", "Australia", "Úc", "Uc"),
    "BLR": _country("BLR", "Belarus"),
    "BLZ": _country("BLZ", "Belize"),
    "BOL": _country("BOL", "Bolivia"),
    "BWA": _country("BWA", "Botswana"),
    "BRA": _country("BRA", "Brazil", "Brasil"),
    "BRN": _country("BRN", "Brunei", "Brunei Darussalam"),
    "KHM": _country("KHM", "Cambodia", "Campuchia", "Cam-pu-chia"),
    "CAN": _country("CAN", "Canada"),
    "TCD": _country("TCD", "Chad"),
    "CHL": _country("CHL", "Chile"),
    "CHN": _country("CHN", "China", "Trung Quốc", "Trung Quoc"),
    "COL": _country("COL", "Colombia"),
    "CRI": _country("CRI", "Costa Rica"),
    "CUB": _country("CUB", "Cuba"),
    "DOM": _country("DOM", "Dominican Republic"),
    "ECU": _country("ECU", "Ecuador"),
    "EGY": _country("EGY", "Egypt", "Ai Cập", "Ai Cap"),
    "SLV": _country("SLV", "El Salvador"),
    "ETH": _country("ETH", "Ethiopia"),
    "FIN": _country("FIN", "Finland"),
    "FRA": _country("FRA", "France", "Pháp", "Phap"),
    "DEU": _country("DEU", "Germany", "Deutschland", "Đức", "Duc"),
    "GRC": _country("GRC", "Greece", "Hy Lạp", "Hy Lap"),
    "GTM": _country("GTM", "Guatemala"),
    "GUY": _country("GUY", "Guyana"),
    "HTI": _country("HTI", "Haiti"),
    "HND": _country("HND", "Honduras"),
    "ISL": _country("ISL", "Iceland"),
    "IND": _country("IND", "India", "Ấn Độ", "An Do"),
    "IDN": _country("IDN", "Indonesia", "Indo"),
    "IRN": _country("IRN", "Iran"),
    "IRL": _country("IRL", "Ireland", "Ai Len"),
    "ITA": _country("ITA", "Italy", "Italia", "Ý"),
    "JAM": _country("JAM", "Jamaica"),
    "JPN": _country("JPN", "Japan", "Nhật Bản", "Nhat Ban"),
    "KAZ": _country("KAZ", "Kazakhstan"),
    "KEN": _country("KEN", "Kenya"),
    "LAO": _country("LAO", "Laos", "Lào", "Lao"),
    "LBY": _country("LBY", "Libya"),
    "MDG": _country("MDG", "Madagascar"),
    "MYS": _country("MYS", "Malaysia"),
    "MLI": _country("MLI", "Mali"),
    "MRT": _country("MRT", "Mauritania"),
    "MEX": _country("MEX", "Mexico"),
    "MNG": _country("MNG", "Mongolia"),
    "MAR": _country("MAR", "Morocco"),
    "MOZ": _country("MOZ", "Mozambique"),
    "MMR": _country("MMR", "Myanmar"),
    "NAM": _country("NAM", "Namibia"),
    "NZL": _country("NZL", "New Zealand"),
    "NIC": _country("NIC", "Nicaragua"),
    "NER": _country("NER", "Niger"),
    "NGA": _country("NGA", "Nigeria"),
    "NOR": _country("NOR", "Norway"),
    "OMN": _country("OMN", "Oman"),
    "PAK": _country("PAK", "Pakistan"),
    "PAN": _country("PAN", "Panama"),
    "PNG": _country("PNG", "Papua New Guinea"),
    "PRY": _country("PRY", "Paraguay"),
    "PER": _country("PER", "Peru"),
    "PHL": _country("PHL", "Philippines", "Philippine", "Phil", "Phi lip pin"),
    "POL": _country("POL", "Poland"),
    "PRT": _country("PRT", "Portugal"),
    "ROU": _country("ROU", "Romania"),
    "RUS": _country("RUS", "Russia", "Nga"),
    "SAU": _country("SAU", "Saudi Arabia"),
    "SGP": _country("SGP", "Singapore", "Xin-ga-po", "Singapura"),
    "ZAF": _country("ZAF", "South Africa"),
    "KOR": _country("KOR", "South Korea", "Korea", "Hàn Quốc", "Han Quoc"),
    "ESP": _country("ESP", "Spain", "Tây Ban Nha", "Tay Ban Nha"),
    "SDN": _country("SDN", "Sudan"),
    "SUR": _country("SUR", "Suriname"),
    "SWE": _country("SWE", "Sweden"),
    "TZA": _country("TZA", "Tanzania"),
    "THA": _country("THA", "Thailand", "Thái Lan", "Thai Lan"),
    "TUR": _country("TUR", "Turkey", "Turkiye", "Thổ Nhĩ Kỳ", "Tho Nhi Ky"),
    "UKR": _country("UKR", "Ukraine"),
    "GBR": _country("GBR", "United Kingdom", "UK", "Britain", "Anh"),
    "USA": _country("USA", "United States", "United States of America", "America", "US", "U.S.", "Mỹ", "My"),
    "URY": _country("URY", "Uruguay"),
    "VEN": _country("VEN", "Venezuela"),
    "VNM": _country("VNM", "Vietnam", "Viet Nam", "Việt Nam", "VN"),
    "YEM": _country("YEM", "Yemen"),
    "ZMB": _country("ZMB", "Zambia"),
    "ZWE": _country("ZWE", "Zimbabwe"),
}


@dataclass(frozen=True)
class CountryMatch:
    country: CountryMeta
    matched_alias: str


def _contains_country_alias(normalized_text: str, normalized_alias: str) -> bool:
    if not normalized_alias:
        return False

    return re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text) is not None


def _contains_iso3_token(raw_text: str, code: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", raw_text) is not None


def _alias_position(normalized_text: str, alias: str) -> int:
    normalized_alias = normalize_text(alias)
    if not normalized_alias:
        return 10**9
    match = re.search(rf"(^|\s){re.escape(normalized_alias)}($|\s)", normalized_text)
    if match:
        return match.start()
    return 10**9


def resolve_countries(message: str) -> list[CountryMatch]:
    normalized_message = normalize_text(message)
    matches: list[CountryMatch] = []

    for country in COUNTRIES.values():
        if _contains_iso3_token(message, country.code):
            matches.append(CountryMatch(country=country, matched_alias=country.code))
            continue

        aliases = sorted(
            {
                alias
                for alias in (country.name, *country.aliases)
                if alias and alias != country.code
            },
            key=lambda item: len(normalize_text(item)),
            reverse=True,
        )

        for alias in aliases:
            normalized_alias = normalize_text(alias)

            if _contains_country_alias(normalized_message, normalized_alias):
                matches.append(CountryMatch(country=country, matched_alias=alias))
                break

    seen: set[str] = set()
    unique_matches: list[CountryMatch] = []

    for match in matches:
        if match.country.code not in seen:
            seen.add(match.country.code)
            unique_matches.append(match)

    unique_matches.sort(key=lambda match: _alias_position(normalized_message, match.matched_alias))
    return unique_matches


def country_match_to_dict(match: CountryMatch) -> dict:
    data = asdict(match.country)
    data["matched_alias"] = match.matched_alias
    return data
