# agent-skills

신규 프로젝트 설계, 기존 프로젝트 유지보수, 오픈소스 기여를 위한 에이전트 스킬 모음이다. Codex CLI와 Claude Code에서 같은 `skills/` 원본을 같은 흐름으로 사용한다.

핵심 원칙: **세션 하나가 Issue 하나를 처리한다.** 병렬 작업은 터미널을 더 여는 것이다.

## 설치

`skills/`의 각 스킬을 두 CLI의 전역 스킬 경로에 심볼릭 링크로 연결한다. 기존 항목은 덮어쓰지 않는다.

```bash
cd ~/src/agent-skills
for dir in ~/.agents/skills ~/.claude/skills; do
  mkdir -p "$dir"
  for skill in skills/*/; do
    name=$(basename "$skill")
    [ -e "$dir/$name" ] || [ -L "$dir/$name" ] || ln -s "$PWD/skills/$name" "$dir/$name"
  done
done
```

- 요구 사항: Git, Python 3.10 이상, GitHub CLI(`gh auth login`). `$explain-diff`는 Notion MCP가 필요하다. Linux, macOS, WSL에서 동작한다.
- 호출: Codex는 `$skill-name`, Claude Code는 `/skill-name`. 아래 예시는 Codex 표기다. `$work-issue`와 `$explain-diff`는 직접 호출할 때만 실행된다.
- Codex는 작업할 저장소의 루트에서 실행하고, commit과 worktree 생성 및 `$create-pr`의 `git push -u` 승인 요청을 위한 규칙 파일을 한 번 설치한다. Push와 PR 게시는 `$create-pr`에 대한 명시적 요청이 필요하다.

```bash
mkdir -p ~/.codex/rules
sed "s|@AGENT_SKILLS@|$PWD|g" templates/codex/agent-workflow.rules > ~/.codex/rules/agent-workflow.rules
```

## 스킬

| Skill | 역할 |
| --- | --- |
| `$plan-change` | 기존 코드를 조사하고 해결 방향을 합의해 GitHub Issue를 만든다. |
| `$order-issues` | 열린 Issue의 의존성을 분석해 작업 순서를 알려 준다. 작업은 하지 않는다. |
| `$work-issue` | Issue 하나를 계획 → 구현 → PR까지 진행한다. |
| `$plan-tasks` | 승인된 Issue나 계획 하나를 순차 Task로 나눈다. |
| `$execute-tasks` | Task를 하나씩 구현, 검증, commit한다. |
| `$create-pr` | 검증된 브랜치를 push하고 PR을 만든다. |
| `$repair-pr` | PR의 리뷰 지적, conflict, CI 실패를 고친다. |
| `$cleanup-branch` | 병합이 확인된 브랜치와 worktree를 정리한다. |
| `$explain-diff` | PR 전 변경을 설명하는 Notion 학습 페이지를 만든다. |
| `$init-project` | `PROJECT_BRIEF.md`로 신규 프로젝트의 PRD와 아키텍처를 설계한다. |
| `$contribute` | 지정한 upstream Issue 하나의 기여 방안을 설계한다. |
| `$write-ste` | 기술 문서와 Issue, PR 문구를 명확하게 다듬는다. |

## 사용 흐름

### 기존 프로젝트 유지보수

```text
1. Issue 만들기     $plan-change 만료된 토큰 요청이 500을 반환한다. 원인을 조사하고 해결 방향을 정하자.
2. 순서 확인        $order-issues
3. Issue 처리       $work-issue 3            (Issue마다 터미널 하나)
4. PR 병합 후       $order-issues            (다음에 시작할 Issue 확인)
5. 정리             $cleanup-branch
```

- `$plan-change`는 Issue 사이의 선행 관계를 본문의 `- Depends on: #N` 줄로 기록한다. Issue만 만들고 세션을 끝내도 된다.
- `$order-issues`는 어느 세션에서 실행해도 같은 결과를 낸다. 예: #2는 #3에, #1은 #4에 의존할 때

  ```text
  Track 1: #3 -> #2
  Track 2: #4 -> #1
  Start now (one terminal each): #3, #4
  Single-terminal order: #3 -> #2 -> #4 -> #1
  ```

- `$work-issue`는 계획 승인과 PR 승인을 같은 세션에서 묻는다. 언제든 끼어들어 방향을 바꿀 수 있다.
- 단위 스킬을 직접 써도 된다: `$plan-tasks <Issue URL>` → `$execute-tasks <plan 경로>` → `$create-pr`.

### 병렬 실행

```text
(터미널 1, claude) /work-issue 3
(터미널 2, codex)  $work-issue 4
```

- `Start now`에 나온 Issue를 터미널마다 하나씩 실행한다. CLI는 남은 사용량에 맞춰 고른다.
- Issue마다 worktree(`.worktrees/issue-<N>`)와 브랜치가 따로 있어 작업이 섞이지 않는다. 같은 Issue는 두 세션에서 동시에 실행되지 않는다.
- 먼저 병합된 PR 때문에 다른 PR에 conflict가 생기면 `$repair-pr <PR>`로 고친다.

### 중단 후 이어가기

세션이 멈춰도(사용량 한도, 터미널 종료) commit과 진행 기록은 남는다. 어느 CLI에서든 `$work-issue <N>`을 다시 실행하면 남은 단계부터 이어간다. 멈춘 세션의 점유는 확인을 받은 뒤 해제한다.

### 신규 프로젝트

[PROJECT_BRIEF.template.md](templates/PROJECT_BRIEF.template.md)로 `PROJECT_BRIEF.md`를 준비한다.

```text
$init-project PROJECT_BRIEF.md를 바탕으로 PRD와 아키텍처를 설계하자.
$plan-tasks 승인된 docs/PRD.md와 docs/ARCHITECTURE.md로 Task를 작성해.
$execute-tasks docs/TASKS.md를 실행해.
$create-pr
```

### 오픈소스 기여

```text
$contribute https://github.com/OWNER/REPO/issues/123
$plan-tasks <$contribute가 알려 준 CONTRIBUTION_PLAN.md 경로>
$execute-tasks <TASKS.md 경로>
$create-pr
```

계획과 Task 파일은 upstream 저장소의 Git 추적 밖에 저장된다.

### 선택 기능

- PR 전에 변경을 복습하려면 `$explain-diff`를 실행한다. 학습 자료일 뿐 검증이나 승인을 대신하지 않는다.
- `$work-issue`의 단계(`precheck → plan → execute → explain(선택) → pr`)는 저장소의 `.agent-workflow/pipeline.json`으로 바꿀 수 있다. 형식은 [stage-contract.md](skills/work-issue/references/stage-contract.md)를 참고한다.

## 규칙

- Issue 생성, push, PR 생성, 댓글, merge에는 각각 사용자 승인이 필요하다. 스킬은 merge하지 않는다.
- 계획 스킬은 코드를 구현하지 않는다.
- 사용자의 작업을 자동으로 reset, clean, stash하지 않는다.
- 승인 요청과 설명은 한국어로, GitHub에 게시하는 제목과 본문은 영어로 쓴다.
