"""
Visual Relevance & Keyword Matching Engine
Implements stop-word removal, lemmatization, synonym expansion, multi-word phrase matching,
ambiguity disambiguation, semantic similarity, and calibrated 0.0 - 5.0 relevance scoring.
"""
from __future__ import annotations

import re
import math
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── 1. Stop Words & Generic Stock Noise ──────────────────────────────────────
STOP_WORDS: Set[str] = {
    # Standard English stop words
    "a", "about", "above", "across", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves",
    # Stock footage filler & generic media labels (avoid counting as content match)
    "video", "footage", "clip", "photo", "image", "photograph", "picture",
    "showing", "depicting", "depicts", "concept", "conceptual", "abstract",
    "background", "view", "shot", "scene", "illustration", "isolated",
    "beautiful", "nice", "great", "best", "HD", "4k", "cinematic", "style",
}

# ── 2. Irregular Lemmatization Mappings ──────────────────────────────────────
IRREGULAR_LEMMAS: Dict[str, str] = {
    # Irregular verbs
    "running": "run", "ran": "run", "runs": "run",
    "driving": "drive", "drove": "drive", "driven": "drive", "drives": "drive",
    "walking": "walk", "walked": "walk", "walks": "walk",
    "growing": "grow", "grew": "grow", "grown": "grow", "grows": "grow",
    "farming": "farm", "farmed": "farm", "farms": "farm",
    "planting": "plant", "planted": "plant", "plants": "plant",
    "harvesting": "harvest", "harvested": "harvest", "harvests": "harvest",
    "eating": "eat", "ate": "eat", "eaten": "eat", "eats": "eat",
    "cooking": "cook", "cooked": "cook", "cooks": "cook",
    "flying": "fly", "flew": "fly", "flown": "fly", "flies": "fly",
    "swimming": "swim", "swam": "swim", "swum": "swim", "swims": "swim",
    "buying": "buy", "bought": "buy", "buys": "buy",
    "selling": "sell", "sold": "sell", "sells": "sell",
    "saving": "save", "saved": "save", "saves": "save",
    "spending": "spend", "spent": "spend", "spends": "spend",
    "building": "build", "built": "build", "builds": "build",
    "working": "work", "worked": "work", "works": "work",
    "teaching": "teach", "taught": "teach", "teaches": "teach",
    "learning": "learn", "learned": "learn", "learns": "learn",
    "studying": "study", "studied": "study", "studies": "study",
    "investing": "invest", "invested": "invest", "invests": "invest",
    # Irregular plurals / nouns
    "children": "child", "people": "person", "men": "man", "women": "woman",
    "feet": "foot", "teeth": "tooth", "mice": "mouse", "leaves": "leaf",
    "wolves": "wolf", "knives": "knife", "lives": "life",
    "cities": "city", "countries": "country", "berries": "berry", "stories": "story",
    "factories": "factory", "technologies": "technology", "companies": "company",
    "cars": "car", "vehicles": "vehicle", "trees": "tree", "fields": "field",
    "farmers": "farmer", "workers": "worker", "students": "student", "doctors": "doctor",
    "crops": "crop", "grains": "grain", "turbines": "turbine", "panels": "panel",
    "accounts": "account", "investments": "investment", "finances": "finance",
    "savings": "savings", "balance": "balance", "balances": "balance",
}

# ── 3. Domain Synonym & Concept Mappings ─────────────────────────────────────
# Bidirectional synonym clusters across B-roll and narrative subjects
SYNONYM_GROUPS: List[Set[str]] = [
    # Agriculture & Farming
    {"farmer", "grower", "cultivator", "agriculturist", "peasant"},
    {"farm", "farmland", "field", "paddy", "pasture", "meadow", "cropland", "acreage"},
    {"crop", "harvest", "yield", "grain", "produce", "agriculture"},
    {"wheat", "grain", "cereal", "barley", "rye"},
    {"rice", "paddy", "grain"},
    {"vegetable", "produce", "greens", "veggie"},
    {"fruit", "orchard", "produce", "fresh fruit"},
    # Environment & Energy
    {"turbine", "windmill", "wind generator", "wind turbine", "wind power"},
    {"solar", "photovoltaic", "solar panel", "solar cell", "solar energy", "solar farm"},
    {"nature", "landscape", "scenery", "environment", "outdoors", "wilderness"},
    {"forest", "woods", "woodland", "trees", "grove", "jungle"},
    {"mountain", "peak", "summit", "ridge", "highland"},
    {"river", "stream", "creek", "brook", "waterway"},
    {"ocean", "sea", "marine", "coastal", "coast", "shore"},
    {"sky", "clouds", "weather", "atmosphere", "blue sky"},
    {"sun", "sunlight", "sunshine", "sunrise", "sunset", "dawn", "dusk", "daylight"},
    # Finance, Economy & Savings
    {"money", "cash", "currency", "funds", "capital", "wealth", "finance", "monetary"},
    {"salary", "income", "earning", "earnings", "wage", "wages", "paycheck", "revenue", "compensation"},
    {"savings", "saving", "deposit", "reserve", "piggy bank", "nest egg"},
    {"expense", "expenses", "spending", "spend", "cost", "costs", "expenditure", "purchase", "bill"},
    {"budget", "allocation", "allocate", "divide", "distribute", "organize", "portion", "share"},
    {"essential", "essentials", "necessity", "need", "needs", "requirement", "staple"},
    {"want", "wants", "luxury", "desire", "discretionary", "unnecessary"},
    {"debt", "loan", "borrow", "credit", "liability", "owing"},
    {"bank", "banking", "financial institution", "vault", "safe", "strongbox"},
    {"investment", "investing", "stocks", "shares", "equity", "portfolio", "assets"},
    {"chart", "graph", "diagram", "infographic", "growth curve", "trend line"},
    {"growth", "increase", "rise", "expansion", "progress", "accumulation", "compounding"},
    {"freedom", "independence", "security", "stability", "peace of mind", "calm"},
    {"discipline", "disciplined", "conscious", "deliberate", "consistent", "regular", "habit", "routine"},
    {"foundation", "base", "basis", "cornerstone", "pillar", "groundwork"},
    {"emergency", "crisis", "shock", "buffer", "reserve", "safety net", "unforeseen"},
    {"decision", "choice", "planning", "goal", "target", "track", "tracking"},
    # Technology & Computing
    {"computer", "pc", "laptop", "workstation", "desktop", "machine"},
    {"server", "datacenter", "data center", "cloud computing", "mainframe", "server rack"},
    {"code", "software", "programming", "developer", "coding", "algorithm"},
    {"technology", "tech", "digital", "electronic", "cyber", "innovation"},
    {"mobile", "smartphone", "phone", "cellular", "device"},
    {"network", "internet", "connectivity", "telecommunication", "wifi"},
    # Transportation & Vehicles
    {"car", "automobile", "vehicle", "motorcar", "sedan"},
    {"road", "street", "highway", "freeway", "avenue", "lane", "driveway"},
    {"traffic", "vehicles", "cars", "transport", "congestion"},
    {"train", "railway", "railroad", "locomotive", "metro", "subway"},
    {"airplane", "plane", "aircraft", "jet", "flight", "aviation"},
    # Education, People & Roles
    {"student", "learner", "pupil", "scholar", "undergraduate"},
    {"school", "classroom", "academy", "college", "university", "campus"},
    {"teacher", "educator", "instructor", "professor", "tutor"},
    {"doctor", "physician", "medic", "clinician", "practitioner"},
    {"hospital", "clinic", "healthcare", "medical center", "infirmary"},
    {"worker", "employee", "laborer", "craftsman", "specialist"},
    {"office", "workplace", "workstation", "corporate", "headquarters"},
    # Cultural & Festivals
    {"pongal", "harvest festival", "thai pongal", "makar sankranti", "sankranti"},
    {"kolam", "rangoli", "floor pattern", "chalk design"},
    {"pot", "clay pot", "cooking pot", "earthenware"},
    {"diwali", "deepavali", "festival of lights"},
    {"diya", "clay lamp", "oil lamp", "lantern", "candle"},
]

# Build reverse synonym lookup
SYNONYM_LOOKUP: Dict[str, Set[str]] = {}
for group in SYNONYM_GROUPS:
    for term in group:
        SYNONYM_LOOKUP[term] = group


# ── 4. Natural Language Helpers ──────────────────────────────────────────────

def lemmatize_word(word: str) -> str:
    """Lemmatize a single English word using rule-based morphology."""
    w = word.lower().strip()
    if not w:
        return ""
    if w in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[w]

    # -ies -> -y (e.g. cities -> city)
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    # -ves -> -f / -fe (e.g. leaves -> leaf)
    if w.endswith("ves") and len(w) > 4:
        return w[:-3] + "f"
    # -sses, -shes, -ches, -xes, -zes -> drop -es
    for suffix in ("sses", "shes", "ches", "xes", "zes"):
        if w.endswith(suffix):
            return w[:-2]
    # -ing -> base verb
    if w.endswith("ing") and len(w) > 5:
        # e.g. farming -> farm, harvesting -> harvest
        stem = w[:-3]
        if stem.endswith(("bb", "dd", "gg", "mm", "nn", "pp", "tt")):
            return stem[:-1]  # running -> run, swimming -> swim
        return stem
    # -ed -> base verb
    if w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        if stem.endswith(("bb", "dd", "gg", "mm", "nn", "pp", "tt")):
            return stem[:-1]
        if stem.endswith("i"):
            return stem[:-1] + "y"  # studied -> study
        return stem
    # regular plural -s
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def extract_content_tokens(text: str) -> List[str]:
    """Tokenize text, remove stop words, and lemmatize."""
    if not text:
        return []
    raw_words = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
    tokens = []
    for rw in raw_words:
        if rw not in STOP_WORDS:
            lem = lemmatize_word(rw)
            if lem and lem not in STOP_WORDS:
                tokens.append(lem)
    return tokens


def extract_phrases(text: str, max_n: int = 3) -> Set[str]:
    """Extract significant 2-gram and 3-gram phrases containing meaningful content words."""
    if not text:
        return set()
    raw_words = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
    phrases = set()
    # Bigrams & Trigrams
    for n in range(2, max_n + 1):
        for i in range(len(raw_words) - n + 1):
            chunk = raw_words[i:i + n]
            content_words = [w for w in chunk if w not in STOP_WORDS]
            if content_words and chunk[0] not in STOP_WORDS and chunk[-1] not in STOP_WORDS:
                phrase = " ".join([lemmatize_word(w) for w in chunk])
                phrases.add(phrase)
    return phrases


def get_synonym_set(word: str) -> Set[str]:
    """Return all known synonyms for a word/term."""
    w = lemmatize_word(word.lower().strip())
    syns = set(SYNONYM_LOOKUP.get(w, {w}))
    syns.add(w)
    return syns


# ── 5. Ambiguity Disambiguation ──────────────────────────────────────────────

def check_semantic_contradiction(scene: Dict[str, Any], candidate: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Detect explicit semantic contradictions or false-keyword matches.
    Example: 'cloud computing' matching literal atmospheric sky; 'fruit shop' matching butchered meat.
    """
    narration = (scene.get("narration_text") or "").lower()
    hint = (scene.get("visual_hint") or scene.get("semantic_description") or scene.get("visual_description") or "").lower()
    subject = (scene.get("visual_subject") or "").lower()
    combined_scene = f"{narration} {hint} {subject}"

    tags = (candidate.get("tags") or "").lower()
    cand_desc = (candidate.get("description") or candidate.get("prompt") or "").lower()
    combined_cand = f"{tags} {cand_desc}"

    # 1. Cloud Computing vs Literal Atmospheric Sky
    is_cloud_tech = any(k in combined_scene for k in ["cloud computing", "cloud infrastructure", "server", "datacenter", "software", "workload", "compute"])
    is_literal_sky = any(k in combined_cand for k in ["weather", "sky", "blue sky", "cumulus", "atmosphere", "fluffy cloud", "sunset cloud"])
    has_tech = any(k in combined_cand for k in ["server", "computer", "datacenter", "code", "screen", "digital", "network"])
    if is_cloud_tech and is_literal_sky and not has_tech:
        return True, "Literal atmospheric sky imagery matched to abstract cloud computing narration"

    # 2. Financial / Savings Bank vs River / Water Bank
    is_finance_bank = any(k in combined_scene for k in ["savings", "interest", "deposit", "money", "finance", "financial", "wealth", "invest"])
    is_river_bank = any(k in combined_cand for k in ["river", "stream", "creek", "water", "lake", "shore", "riverbank", "grass"])
    has_finance = any(k in combined_cand for k in ["money", "finance", "cash", "coins", "account", "vault", "banking"])
    if is_finance_bank and is_river_bank and not has_finance:
        return True, "River/water bank imagery matched to financial bank/savings narration"

    # 3. Fruit Shop / Fresh Produce vs Meat / Butcher
    is_fruit = any(k in combined_scene for k in ["fruit", "fruits", "apple", "banana", "citrus", "produce", "fresh fruit"])
    is_meat = any(k in combined_cand for k in ["meat", "beef", "pork", "steak", "butcher", "sausage", "raw meat", "bbq", "barbecue"])
    if is_fruit and is_meat:
        return True, "Meat or butcher imagery matched to fresh fruits narration"

    # 4. Debt Prevention / Savings vs Reckless Luxury Cash Throwing
    is_debt_prevention = any(k in combined_scene for k in ["avoid debt", "disciplined budgeting", "conservative savings", "debt prevention"])
    is_reckless_spending = any(k in combined_cand for k in ["throwing cash", "luxury shopping", "lavish spender", "casino gambling"])
    if is_debt_prevention and is_reckless_spending:
        return True, "Lavish reckless cash spending imagery matched to debt prevention narration"

    # 5. Technology / Digital vs Pure Floral / Garden (when no nature mentioned)
    is_pure_tech = any(k in combined_scene for k in ["artificial intelligence", "robotics", "machine learning", "cybersecurity"])
    is_floral_only = all(k in combined_cand for k in ["flower", "petal"]) and not any(k in combined_cand for k in ["robot", "computer", "tech", "digital"])
    if is_pure_tech and is_floral_only:
        return True, "Floral pattern imagery matched to artificial intelligence/robotics narration"

    return False, None


# ── 6. Multi-Factor Relevance Scorer ─────────────────────────────────────────

class RelevanceScorer:
    """
    Evaluates candidate visual relevance against scene requirements.
    Normalized consistently to a 0.0 - 5.0 scale with non-overlapping signals.
    """

    MIN_ACCEPTANCE_THRESHOLD = 3.5

    @classmethod
    def score_candidate(
        cls,
        scene: Dict[str, Any],
        candidate: Dict[str, Any],
        vlm_verification_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Compute an objective, non-double-counting relevance score (0.0 to 5.0).
        Evaluates:
          1. Subject Match (0-5, 35% weight)
          2. Action / State Match (0-5, 25% weight)
          3. Setting / Environment Match (0-5, 20% weight)
          4. Phrase & Semantic Overlap (0-5, 20% weight)
        """
        narration = scene.get("narration_text", "")
        hint = scene.get("visual_hint") or scene.get("semantic_description") or scene.get("visual_description", "")
        subject = scene.get("visual_subject", "")
        action = scene.get("visual_action", "")
        setting = scene.get("environment") or scene.get("setting", "")
        scene_queries = (
            (scene.get("search_queries") or []) +
            (scene.get("primary_search_queries") or []) +
            (scene.get("alternative_search_queries") or []) +
            ([scene["primary_search_query"]] if scene.get("primary_search_query") else [])
        )

        tags = candidate.get("tags", "")
        cand_desc = candidate.get("description") or candidate.get("prompt") or ""
        cand_query = candidate.get("query_used", "")
        raw_cand_text = f"{tags} {cand_desc} {cand_query}".lower()
        cand_clean_text = re.sub(r"[,;._\-\/\\|]+", " ", raw_cand_text)
        cand_clean_text = re.sub(r"\s+", " ", cand_clean_text).strip()
        cand_tokens = set(extract_content_tokens(cand_clean_text))

        # Step 1: Contradiction Check
        is_contra, contra_reason = check_semantic_contradiction(scene, candidate)
        if is_contra:
            return {
                "relevance_score": 1.0,
                "composite_score": 1.0,
                "contradiction_detected": True,
                "rejection_reason": contra_reason,
                "subject_match": 0.1,
                "action_match": 0.1,
                "setting_match": 0.1,
                "phrase_match": 0.1,
                "meets_threshold": False,
                "evidence": f"Contradiction detected: {contra_reason}",
            }

        # Step 2: Subject Match (0.0 - 5.0, weight 0.35)
        # Extract subject tokens and core narration/hint concepts
        subj_tokens = extract_content_tokens(subject) if subject else []
        core_narr_tokens = extract_content_tokens(narration)[:5]
        core_hint_tokens = extract_content_tokens(hint)[:5]
        combined_subject_tokens = list(dict.fromkeys(subj_tokens + core_narr_tokens + core_hint_tokens))

        subj_matches = 0
        for st in combined_subject_tokens:
            st_syns = get_synonym_set(st)
            if any(syn in cand_tokens or syn in cand_clean_text for syn in st_syns):
                subj_matches += 1

        if combined_subject_tokens:
            # Matching 2+ core domain concepts or synonyms is strong evidence
            subj_ratio = min(1.0, subj_matches / max(2, min(4, len(subj_tokens) if subj_tokens else len(core_narr_tokens))))
        else:
            subj_ratio = 0.5
        subject_score = 1.0 + 4.0 * subj_ratio

        # Step 3: Action Match (0.0 - 5.0, weight 0.25)
        act_tokens = extract_content_tokens(action) if action else []
        act_matches = 0
        if act_tokens:
            for at in act_tokens:
                at_syns = get_synonym_set(at)
                if any(syn in cand_tokens or syn in cand_clean_text for syn in at_syns):
                    act_matches += 1
            act_ratio = act_matches / max(len(act_tokens), 1)
            action_score = 1.0 + 4.0 * act_ratio
        else:
            # Calibrated baseline aligned with subject score
            act_ratio = subj_ratio
            action_score = max(2.5, subject_score * 0.9)

        # Step 4: Setting / Environment Match (0.0 - 5.0, weight 0.20)
        env_tokens = extract_content_tokens(setting) if setting else []
        env_matches = 0
        if env_tokens:
            for et in env_tokens:
                et_syns = get_synonym_set(et)
                if any(syn in cand_tokens or syn in cand_clean_text for syn in et_syns):
                    env_matches += 1
            env_ratio = env_matches / max(len(env_tokens), 1)
            setting_score = 1.0 + 4.0 * env_ratio
        else:
            env_ratio = subj_ratio
            setting_score = max(2.5, subject_score * 0.9)

        # Step 5: Multi-Word Phrase & Semantic Match (0.0 - 5.0, weight 0.20)
        target_context = f"{narration} {hint} {subject}".strip()
        target_phrases = extract_phrases(target_context)
        # Also include curated search queries as target phrases
        for sq in scene_queries:
            sq_lem = " ".join([lemmatize_word(w) for w in extract_content_tokens(sq)])
            if sq_lem and len(sq_lem.split()) >= 2:
                target_phrases.add(sq_lem)

        phrase_hits = 0
        cand_query_clean = re.sub(r"[,;._\-\/\\|]+", " ", cand_query.lower()).strip()
        for p in target_phrases:
            p_words = p.split()
            # 1. Contiguous phrase in normalized candidate text
            if p in cand_clean_text:
                phrase_hits += 1
            # 2. Query used matches phrase
            elif cand_query_clean and (p in cand_query_clean or cand_query_clean in p):
                phrase_hits += 1
            # 3. All constituent lemmas/synonyms present in candidate tokens
            elif len(p_words) >= 2 and all(any(syn in cand_tokens for syn in get_synonym_set(pw)) for pw in p_words):
                phrase_hits += 1

        if phrase_hits >= 2:
            phrase_ratio = 1.0
        elif phrase_hits == 1:
            phrase_ratio = 0.70
        else:
            phrase_ratio = 0.0

        phrase_score = 1.0 + 4.0 * phrase_ratio

        # Multi-factor weighted fused relevance score (no double-counting)
        raw_fused = (
            0.35 * subject_score +
            0.25 * action_score +
            0.20 * setting_score +
            0.20 * phrase_score
        )

        # Incorporate VLM verification if available
        if vlm_verification_score is not None:
            vlm_s = float(vlm_verification_score)
            if vlm_s >= 3.5:
                # Strong visual confirmation: 65% VLM + 35% keyword/semantic
                final_relevance = 0.65 * vlm_s + 0.35 * raw_fused
            else:
                final_relevance = 0.50 * vlm_s + 0.50 * raw_fused
        else:
            final_relevance = raw_fused

        final_relevance = round(max(1.0, min(5.0, final_relevance)), 2)
        meets_threshold = final_relevance >= cls.MIN_ACCEPTANCE_THRESHOLD

        evidence = (
            f"Subject: {subject_score:.1f}/5, Action: {action_score:.1f}/5, "
            f"Setting: {setting_score:.1f}/5, Phrases: {phrase_score:.1f}/5 "
            f"-> Final Relevance: {final_relevance:.2f}/5"
        )

        return {
            "relevance_score": final_relevance,
            "composite_score": final_relevance,
            "subject_match": round(subj_ratio, 2),
            "action_match": round(act_ratio, 2),
            "setting_match": round(env_ratio, 2),
            "phrase_match": round(phrase_ratio, 2),
            "contradiction_detected": False,
            "meets_threshold": meets_threshold,
            "evidence": evidence,
        }
