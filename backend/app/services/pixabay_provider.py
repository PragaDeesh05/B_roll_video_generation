"""
Pixabay Footage Provider
Handles stock video search, ranking, deduplication, licensing, and fallback logic.
"""
from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PIXABAY_IMAGE_API = "https://pixabay.com/api/"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos/"
PIXABAY_LICENCE_URL = "https://pixabay.com/service/license-summary/"

# Pixabay Content License: free for commercial and non-commercial use
# No attribution required (encouraged but not mandatory)
PIXABAY_LICENCE = {
    "name": "Pixabay Content License",
    "url": PIXABAY_LICENCE_URL,
    "attribution_required": False,
    "commercial_use_eligible": True,
    "verification_method": "pixabay_api_tos",
    "notes": (
        "Pixabay content is free to use without attribution for commercial and "
        "non-commercial purposes. See https://pixabay.com/service/license-summary/"
    ),
}

# Tags that indicate potential watermark or restricted content
REJECTED_TAGS = {"watermark", "getty", "shutterstock", "adobe stock", "dreamstime"}
REJECTED_USERNAMES = set()  # Populate if known re-uploadders


class PixabayProvider:
    """Dedicated Pixabay footage provider with retry, dedup, and ranking."""

    MAX_PER_QUERY = 20
    REQUEST_TIMEOUT = 15.0
    MAX_RETRIES = 3
    RETRY_DELAY = 1.5

    def __init__(self) -> None:
        if not settings.pixabay_api_key:
            logger.warning("PIXABAY_API_KEY not set – provider will return mock assets.")
            self._mock_mode = True
        else:
            self._mock_mode = False

        self._client = httpx.Client(
            timeout=self.REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        self._cache: Dict[str, List[Dict]] = {}  # query → results

    # ── Public API ────────────────────────────────────────────────────────────

    def retrieve_candidates(
        self,
        scene: Dict[str, Any],
        used_ids: Set[str],
        max_candidates: int = 5,
        download_dir: Optional[Path] = None,
        media_type: str = "both",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve multiple candidate assets for a scene across primary and alternative queries.
        Supports Pixabay video search and high-res stock image search.
        Applies Stage 1 hard constraint filtering (licence, watermarks, avoid tags).
        Optionally downloads candidate media locally when download_dir is specified.
        """
        if self._mock_mode:
            return self._mock_candidates(scene, used_ids, count=max_candidates)

        queries: List[str] = []
        if scene.get("search_queries"):
            queries.extend([q.strip() for q in scene["search_queries"] if q and q.strip()])
        if scene.get("primary_search_queries"):
            queries.extend([q.strip() for q in scene["primary_search_queries"] if q and q.strip()])
        if scene.get("alternative_search_queries"):
            queries.extend([q.strip() for q in scene["alternative_search_queries"] if q and q.strip()])
        if not queries and scene.get("primary_search_query"):
            queries.append(scene["primary_search_query"].strip())

        # Deduplicate queries while preserving order
        unique_queries = []
        seen_q = set()
        for q in queries:
            if q.lower() not in seen_q:
                seen_q.add(q.lower())
                unique_queries.append(q)

        unique_queries = unique_queries[:5]

        collected: List[Dict[str, Any]] = []
        seen_candidate_ids: Set[str] = set()

        for query in unique_queries:
            # Query videos and images according to requested media_type
            hit_tuples: List[Tuple[Dict[str, Any], bool]] = []
            if media_type in ("video", "both"):
                vid_hits = self._search(query)
                for vh in vid_hits:
                    hit_tuples.append((vh, False))
            if media_type in ("image", "both"):
                img_hits = self._search_images(query)
                for ih in img_hits:
                    hit_tuples.append((ih, True))

            query_hits = 0
            for hit, is_image in hit_tuples:
                hit_id = str(hit.get("id", ""))
                cand_id = f"pixabay_{hit_id}"
                if (
                    cand_id in used_ids
                    or cand_id in seen_candidate_ids
                    or hit_id in used_ids
                    or hit_id in seen_candidate_ids
                ):
                    continue

                # Stage 1: Hard constraint filter
                passed, reason = self._check_hard_constraints(hit, scene)
                if not passed:
                    logger.debug(f"Candidate {hit_id} rejected by hard constraints: {reason}")
                    continue

                enriched = self._enrich_image_asset(hit, query) if is_image else self._enrich_asset(hit, query)

                # Download media locally if download_dir is provided
                if download_dir:
                    lazy_mode = getattr(settings, "enable_lazy_downloads", True)
                    if lazy_mode and not is_image:
                        # Video candidate in lazy mode: download ONLY lightweight thumbnail for fast VLM verification
                        thumb_url = enriched.get("thumbnail_url")
                        downloaded_thumb = False
                        if thumb_url:
                            target_thumb = download_dir / f"{enriched['id']}_thumb.jpg"
                            if self._download_file(thumb_url, target_thumb):
                                enriched["extracted_frames"] = [str(target_thumb)]
                                enriched["preview_path"] = str(target_thumb)
                                downloaded_thumb = True
                        if not downloaded_thumb and enriched.get("download_url"):
                            target_file = download_dir / f"{enriched['id']}.mp4"
                            if self._download_file(enriched["download_url"], target_file):
                                enriched["local_path"] = str(target_file)
                                enriched["extracted_frames"] = [str(target_file)]
                    elif enriched.get("download_url"):
                        ext = ".jpg" if is_image else ".mp4"
                        target_file = download_dir / f"{enriched['id']}{ext}"
                        success = self._download_file(enriched["download_url"], target_file)
                        if success:
                            enriched["local_path"] = str(target_file)
                            enriched["extracted_frames"] = [str(target_file)]

                seen_candidate_ids.add(hit_id)
                seen_candidate_ids.add(cand_id)
                collected.append(enriched)
                query_hits += 1
                if query_hits >= 2:
                    break

            if len(collected) >= max_candidates:
                break

        return collected[:max_candidates]

    def _download_file(self, url: str, target_path: Path) -> bool:
        """Download remote asset to local disk with retries and MinIO caching."""
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and target_path.stat().st_size > 5000:
                return True

            # 1. Check MinIO object storage cache first
            cache_key = hashlib.md5(url.encode()).hexdigest()
            try:
                from app.services.storage_service import StorageService
                storage = StorageService()
                cached_file = storage.get_cached_image(cache_key, target_path.parent)
                if cached_file and cached_file.exists() and cached_file.stat().st_size > 5000:
                    if cached_file.resolve() != target_path.resolve():
                        shutil.copy2(cached_file, target_path)
                    logger.info(f"Loaded cached image from MinIO for {url[:50]}...")
                    return True
            except Exception as ce:
                logger.debug(f"MinIO cache lookup bypassed: {ce}")

            # 2. Download from remote if not cached
            for attempt in range(self.MAX_RETRIES):
                try:
                    resp = self._client.get(url, timeout=30.0)
                    if resp.status_code == 429:
                        backoff = self.RETRY_DELAY * (2 ** (attempt + 1))
                        logger.warning(f"Pixabay download rate limit (429) hit, backing off {backoff:.1f}s...")
                        time.sleep(backoff)
                        continue
                    resp.raise_for_status()
                    target_path.write_bytes(resp.content)
                    if target_path.exists() and target_path.stat().st_size > 5000:
                        # 3. Store downloaded image in MinIO cache
                        try:
                            storage.cache_image(target_path, cache_key)
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    logger.warning(f"Download attempt {attempt+1} failed for {url}: {e}")
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))
        except Exception as e:
            logger.error(f"Failed to download asset from {url}: {e}")
        return False

    def _enrich_image_asset(self, asset: Dict, query_used: str) -> Dict:
        """Add provenance, download URL, and relevance fields for Pixabay images."""
        asset_id = str(asset.get("id", ""))
        img_url = asset.get("largeImageURL") or asset.get("webformatURL") or asset.get("previewURL")
        thumb_url = asset.get("previewURL") or asset.get("webformatURL") or img_url
        page_url = asset.get("pageURL", f"https://pixabay.com/photos/{asset_id}/")
        w = asset.get("imageWidth", 1920)
        h = asset.get("imageHeight", 1080)

        return {
            "id": f"pixabay_{asset_id}",
            "query_used": query_used,
            "download_url": img_url,
            "thumbnail_url": thumb_url,
            "page_url": page_url,
            "tags": asset.get("tags", ""),
            "duration": 5.0,
            "width": w,
            "height": h,
            "user": asset.get("user", ""),
            "user_id": str(asset.get("user_id", "")),
            "views": asset.get("views", 0),
            "downloads": asset.get("downloads", 0),
            "likes": asset.get("likes", 0),
            "media_type": "image",
            "provenance": {
                "provider": "pixabay",
                "asset_id": asset_id,
                "original_url": page_url,
                "media_url": img_url,
                "licence_name": PIXABAY_LICENCE["name"],
                "licence_url": PIXABAY_LICENCE["url"],
                "attribution_required": PIXABAY_LICENCE["attribution_required"],
                "attribution_text": f"Image by {asset.get('user', 'Pixabay contributor')} on Pixabay",
                "commercial_use_eligible": PIXABAY_LICENCE["commercial_use_eligible"],
                "verification_status": "provider_policy",
                "verification_method": PIXABAY_LICENCE["verification_method"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "ai_generated": False,
            },
        }

    def _check_hard_constraints(self, asset: Dict[str, Any], scene: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Stage 1: Non-negotiable hard constraints check."""
        asset_id = str(asset.get("id", ""))
        tags = {t.lower().strip() for t in asset.get("tags", "").replace(",", " ").split() if t.strip()}

        # 1. Reject watermarks and known stock watermark agencies
        if tags & REJECTED_TAGS:
            return False, f"Watermarked or restricted tags detected: {tags & REJECTED_TAGS}"

        # 2. Check user against known re-uploaders
        if asset.get("user", "").lower() in REJECTED_USERNAMES:
            return False, f"Prohibited uploader: {asset.get('user')}"

        # 3. Check explicit scene avoid constraints
        avoid_items = [e.lower() for e in (scene.get("must_avoid", []) + scene.get("excluded_visual_elements", []))]
        for item in avoid_items:
            # Check "no real images" / "avoid real photographs"
            if any(term in item for term in ["no real", "avoid real", "not real", "only ai", "illustration only"]):
                return False, "Scene prohibits real filmed footage"

            for tag in tags:
                if item in tag or tag in item:
                    return False, f"Violates scene avoid constraint '{item}' (matched tag '{tag}')"

        # Reject clipart, greeting cards, and text banners when not requested
        unwanted_tags = {"greeting", "postcard", "poster", "invitation", "banner", "seamless pattern"}
        if (tags & unwanted_tags) and not any(ut in str(scene.get("visual_subject", "")).lower() for ut in unwanted_tags):
            if any(t in tags for t in ["vector", "illustration", "card", "drawing"]):
                return False, f"Rejected graphic card / vector clipart ({tags & unwanted_tags})"

        # 4. Domain-specific semantic contradiction checks
        narration_full = (
            str(scene.get("narration_text", "")) + " " +
            str(scene.get("semantic_description", "")) + " " +
            str(scene.get("visual_subject", ""))
        ).lower()

        # Check Fruit vs Meat contradiction
        is_fruit_theme = any(w in narration_full for w in ["fruit", "fruits", "apple", "banana", "orange", "berry", "produce"])
        meat_tags = {"meat", "beef", "pork", "steak", "chicken", "butcher", "raw meat", "bbq", "barbecue"}
        if is_fruit_theme and (tags & meat_tags):
            return False, f"Contradicts fruit scene: contains meat tags {tags & meat_tags}"

        # Check Fruit vs purely floral non-food
        flower_tags = {"flower", "flowers", "bouquet", "floral", "wedding"}
        fruit_tags = {"fruit", "fruits", "apple", "banana", "orange", "berry", "market", "produce", "food", "eat"}
        if is_fruit_theme and (tags & flower_tags) and not (tags & fruit_tags):
            return False, f"Contradicts fruit scene: floral imagery {tags & flower_tags} without fruits"

        # 5. Must have a valid download URL (video stream or image URL)
        has_video = bool(self._best_video_url(asset.get("videos", {})))
        has_image = bool(asset.get("largeImageURL") or asset.get("webformatURL") or asset.get("imageURL"))
        if not has_video and not has_image:
            return False, "No valid downloadable media stream found"

        return True, None

    def search_for_scene(
        self,
        scene: Dict[str, Any],
        used_ids: Set[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Search for the best clip for a scene (backward compatibility method).
        Tries primary query then alternatives, avoids duplicates.
        """
        candidates = self.retrieve_candidates(scene, used_ids, max_candidates=5)
        if candidates:
            best = candidates[0]
            used_ids.add(str(best["id"]))
            return best

        logger.warning(f"No suitable footage found for scene {scene.get('scene_id')}")
        return None

    def get_asset_by_id(self, asset_id: str) -> Optional[Dict]:
        """Fetch a single asset by Pixabay ID."""
        if self._mock_mode:
            return None
        url = f"{PIXABAY_VIDEO_API}?id={asset_id}&key={settings.pixabay_api_key}"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            return hits[0] if hits else None
        except Exception as e:
            logger.error(f"Failed to fetch asset {asset_id}: {e}")
            return None

    # ── Search ────────────────────────────────────────────────────────────────

    def _search_images(self, query: str) -> List[Dict]:
        """Search Pixabay for images matching query, with caching and retry."""
        cache_key = "img_" + hashlib.md5(query.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        params = {
            "key": settings.pixabay_api_key,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "order": "popular",
            "per_page": 10,
            "safesearch": "true",
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self._client.get(PIXABAY_IMAGE_API, params=params)
                resp.raise_for_status()
                data = resp.json()
                hits = data.get("hits", [])
                if not hits:
                    # Fallback to all image types if photo returned 0 hits
                    params["image_type"] = "all"
                    resp_all = self._client.get(PIXABAY_IMAGE_API, params=params)
                    if resp_all.status_code == 200:
                        hits = resp_all.json().get("hits", [])
                self._cache[cache_key] = hits
                return hits
            except httpx.TimeoutException:
                logger.warning(f"Pixabay image search timeout on attempt {attempt+1} for '{query}'")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Pixabay rate limit hit on image search, backing off.")
                    time.sleep(5.0 * (attempt + 1))
                else:
                    logger.error(f"Pixabay image HTTP error: {e}")
                    break
            except Exception as e:
                logger.error(f"Pixabay image search error: {e}")
                break

            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY * (2 ** attempt))

        return []

    def _search(self, query: str) -> List[Dict]:
        """Search Pixabay for videos matching query, with caching and retry."""
        cache_key = hashlib.md5(query.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        params = {
            "key": settings.pixabay_api_key,
            "q": query,
            "video_type": "all",
            "per_page": self.MAX_PER_QUERY,
            "safesearch": "true",
        }

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = self._client.get(PIXABAY_VIDEO_API, params=params)
                resp.raise_for_status()
                data = resp.json()
                hits = data.get("hits", [])
                self._cache[cache_key] = hits
                return hits
            except httpx.TimeoutException:
                logger.warning(f"Pixabay timeout on attempt {attempt+1} for '{query}'")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("Pixabay rate limit hit, backing off.")
                    time.sleep(5.0 * (attempt + 1))
                else:
                    logger.error(f"Pixabay HTTP error: {e}")
                    break
            except Exception as e:
                logger.error(f"Pixabay search error: {e}")
                break

            if attempt < self.MAX_RETRIES - 1:
                time.sleep(self.RETRY_DELAY * (2 ** attempt))

        return []

    # ── Ranking ───────────────────────────────────────────────────────────────

    def _rank_candidates(
        self,
        candidates: List[Dict],
        scene: Dict,
        used_ids: Set[str],
    ) -> List[Dict]:
        """Filter and rank candidates by relevance, quality, and safety."""
        scored = []
        excluded = {e.lower() for e in scene.get("excluded_visual_elements", [])}

        for asset in candidates:
            asset_id = str(asset.get("id", ""))

            # Deduplication
            if asset_id in used_ids:
                continue

            # Watermark / licence check
            tags = {t.lower() for t in asset.get("tags", "").split(", ")}
            if tags & REJECTED_TAGS:
                logger.debug(f"Rejected asset {asset_id} due to tags: {tags & REJECTED_TAGS}")
                continue

            # Check user (known re-uploader)
            if asset.get("user", "").lower() in REJECTED_USERNAMES:
                continue

            # Excluded elements check
            if any(ex in tags for ex in excluded):
                continue

            # Must have a downloadable video
            videos = asset.get("videos", {})
            best_url = self._best_video_url(videos)
            if not best_url:
                continue

            score = self._score_asset(asset, scene, tags)
            if score < 1:
                continue

            scored.append((score, asset))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in scored]

    def _score_asset(self, asset: Dict, scene: Dict, tags: Set[str]) -> float:
        """Heuristic relevance score 0-5 (float) using metadata."""
        score = 0.0

        # Tag overlap with search query
        query_words = set(scene["primary_search_query"].lower().split())
        overlap = len(query_words & tags)
        score += min(overlap * 0.5, 2.0)

        # Prefer longer clips (more likely to have usable segment)
        duration = asset.get("duration", 0)
        if duration >= scene.get("duration", 5):
            score += 1.0
        elif duration > 0:
            score += 0.5

        # View/download count as proxy for quality
        views = asset.get("views", 0)
        if views > 10000:
            score += 1.0
        elif views > 1000:
            score += 0.5

        # Prefer HD or Full HD
        videos = asset.get("videos", {})
        if videos.get("large") or videos.get("full_hd"):
            score += 1.0
        elif videos.get("medium"):
            score += 0.5

        return score

    def _best_video_url(self, videos: Dict) -> Optional[str]:
        """Pick the best available resolution URL (prioritizing 1080p and 720p over massive 4K to minimize download time)."""
        for quality in ("full_hd", "medium", "large", "small", "tiny"):
            v = videos.get(quality, {})
            if isinstance(v, dict) and v.get("url"):
                return v["url"]
        return None

    def _get_video_size(self, videos: Dict) -> tuple[int, int]:
        """Return (width, height) of best available quality (prioritizing 1080p/720p)."""
        for quality in ("full_hd", "medium", "large", "small", "tiny"):
            v = videos.get(quality, {})
            if isinstance(v, dict) and v.get("width") and v.get("height"):
                return v["width"], v["height"]
        return 0, 0

    # ── Provenance ────────────────────────────────────────────────────────────

    def _enrich_asset(self, asset: Dict, query_used: str) -> Dict:
        """Add provenance, download URL, and relevance fields."""
        asset_id = str(asset.get("id", ""))
        videos = asset.get("videos", {})
        best_url = self._best_video_url(videos)
        w, h = self._get_video_size(videos)
        page_url = asset.get("pageURL", f"https://pixabay.com/videos/{asset_id}/")

        picture_id = asset.get("picture_id")
        thumb_url = None
        if picture_id:
            thumb_url = f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"
        if not thumb_url:
            for q in ("tiny", "small", "medium", "large"):
                t = videos.get(q, {}).get("thumbnail")
                if t:
                    thumb_url = t
                    break

        return {
            "id": f"pixabay_{asset_id}",
            "query_used": query_used,
            "download_url": best_url,
            "thumbnail_url": thumb_url,
            "page_url": page_url,
            "tags": asset.get("tags", ""),
            "duration": asset.get("duration", 0),
            "width": w,
            "height": h,
            "user": asset.get("user", ""),
            "user_id": asset.get("user_id", ""),
            "views": asset.get("views", 0),
            "downloads": asset.get("downloads", 0),
            "media_type": "video",
            "provenance": {
                "provider": "pixabay",
                "asset_id": asset_id,
                "original_url": page_url,
                "media_url": best_url,
                "licence_name": PIXABAY_LICENCE["name"],
                "licence_url": PIXABAY_LICENCE["url"],
                "attribution_required": PIXABAY_LICENCE["attribution_required"],
                "attribution_text": f"Video by {asset.get('user', 'Pixabay contributor')} on Pixabay",
                "commercial_use_eligible": PIXABAY_LICENCE["commercial_use_eligible"],
                "verification_status": "provider_policy",
                "verification_method": PIXABAY_LICENCE["verification_method"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "ai_generated": False,
            },
        }

    def download_full_candidate(self, candidate: Dict[str, Any], download_dir: Path) -> Optional[Path]:
        """
        Download the full video or image file ONLY for a selected winning candidate.
        Avoids downloading heavy multi-megabyte videos for rejected candidates.
        """
        # If candidate already has a valid full media file on disk, return it
        loc_p = candidate.get("local_path")
        if loc_p:
            p = Path(loc_p)
            if p.exists() and p.stat().st_size > 5000:
                is_vid = candidate.get("media_type") == "video"
                # If it's a video, ensure it's not merely a preview thumbnail
                if not is_vid or p.suffix.lower() == ".mp4":
                    return p

        download_url = candidate.get("download_url")
        if not download_url:
            return None

        download_dir.mkdir(parents=True, exist_ok=True)
        is_image = candidate.get("media_type") == "image"
        ext = ".jpg" if is_image else ".mp4"
        target_file = download_dir / f"{candidate['id']}{ext}"

        success = self._download_file(download_url, target_file)
        if success:
            candidate["local_path"] = str(target_file)
            candidate["extracted_frames"] = [str(target_file)]
            return target_file
        return None

    def _mock_candidates(self, scene: Dict, used_ids: Set[str], count: int = 3) -> List[Dict]:
        """Return multiple distinct deterministic mock candidates for testing."""
        query = scene.get("primary_search_query") or (scene.get("primary_search_queries", ["nature"])[0])
        candidates = []
        base_hash = hashlib.md5(query.encode()).hexdigest()[:6]

        for idx in range(count):
            cand_id = f"mock_{base_hash}_{idx+1}"
            if cand_id in used_ids:
                cand_id = f"{cand_id}_alt"

            candidates.append({
                "id": cand_id,
                "query_used": query,
                "download_url": None,
                "page_url": f"https://pixabay.com/mock/{cand_id}/",
                "tags": f"{query}, candidate_{idx+1}, visual asset",
                "duration": max(scene.get("duration", 10), 10.0),
                "width": 1920,
                "height": 1080,
                "user": f"mock_artist_{idx+1}",
                "user_id": str(idx + 1),
                "views": 2000 + idx * 500,
                "downloads": 500 + idx * 100,
                "provenance": {
                    "provider": "pixabay",
                    "asset_id": cand_id,
                    "original_url": f"https://pixabay.com/mock/{cand_id}/",
                    "media_url": None,
                    "licence_name": PIXABAY_LICENCE["name"],
                    "licence_url": PIXABAY_LICENCE["url"],
                    "attribution_required": False,
                    "attribution_text": f"Mock candidate {idx+1} (testing mode)",
                    "commercial_use_eligible": True,
                    "verification_status": "mock",
                    "verification_method": "mock_testing",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "ai_generated": False,
                },
            })

        return candidates

    def _mock_asset(self, scene: Dict, used_ids: Set[str]) -> Optional[Dict]:
        """Return a deterministic mock asset for testing without API key."""
        mock_id = hashlib.md5(scene.get("primary_search_query", "").encode()).hexdigest()[:8]
        if mock_id in used_ids:
            mock_id = mock_id + "_alt"
        used_ids.add(mock_id)

        return {
            "id": mock_id,
            "query_used": scene.get("primary_search_query", "nature"),
            "download_url": None,  # No real URL in mock mode
            "page_url": f"https://pixabay.com/mock/{mock_id}/",
            "tags": scene.get("primary_search_query", "nature"),
            "duration": max(scene.get("duration", 10), 10),
            "width": 1920,
            "height": 1080,
            "user": "mock_contributor",
            "user_id": "0",
            "views": 5000,
            "downloads": 1000,
            "provenance": {
                "provider": "pixabay",
                "asset_id": mock_id,
                "original_url": f"https://pixabay.com/mock/{mock_id}/",
                "media_url": None,
                "licence_name": PIXABAY_LICENCE["name"],
                "licence_url": PIXABAY_LICENCE["url"],
                "attribution_required": False,
                "attribution_text": "Mock asset (testing mode)",
                "commercial_use_eligible": True,
                "verification_status": "mock",
                "verification_method": "mock_testing",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "ai_generated": False,
            },
        }

    def close(self) -> None:
        self._client.close()
