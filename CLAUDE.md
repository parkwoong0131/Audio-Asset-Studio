# Audio Asset Studio

프롬프트 기반 게임 오디오 에셋 자동 생성 파이프라인. Game-Asset-Studio의 오디오 버전.

## Phases
1. **phase1_audio_palette** — 장르별 오디오 톤 프리셋 선택
2. **phase2_audio_spec** — 사운드 명세 정규화 + 비용 추정
3. **phase3_prompt_build** — 모델별 generation job 빌드 (레이어/배리에이션)
4. **phase4_generate** — 로컬 MPS/CPU에서 AudioCraft/MusicGen 생성 (해시 캐시)
5. **phase5_post_process** — normalize/trim/fade/loop/layer_mix/format_convert 체인
6. **phase6_engine_import** — Unity 오디오 폴더 + .meta 생성 (Addressables/FMOD/Wwise 지원)

## 실행
```bash
# 전체 파이프라인
python audio_studio.py --project my_clicker --input audio_assets.yaml

# dry-run (Phase 4 생성 스킵)
python audio_studio.py --project my_clicker --input audio_assets.yaml --dry-run

# 부분 실행
python audio_studio.py --project my_clicker --input audio_assets.yaml --phases 5,6

# 레퍼런스 게임 기반
python audio_studio.py --project my_clicker --input audio_assets.yaml --reference cookie-clicker

```

## 카테고리
- SFX: `sfx_ui`, `sfx_reward`, `sfx_impact`, `sfx_ambient`, `sfx_character`, `sfx_notification`
- BGM: `bgm_loop`, `bgm_stinger`, `bgm_adaptive`

## 오디오 팔레트
- `casual_fantasy` — 밝고 경쾌 (클릭커/캐주얼 RPG)
- `pixel_retro` — 8비트 칩튠 (뱀서라이크/아케이드)
- `minimalist_zen` — 미니멀/클린 (퍼즐/2048류)

## 레이어드 SFX
타격감을 위한 멀티레이어 합성: `impact` + `sweetener` + `tail` → 자동 믹스다운

## 후처리 체인
normalize → trim → fade → loop_crossfade → layer_mix → format_convert → sprite_pack
