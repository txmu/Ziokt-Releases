import Init

/-! Publication gates over actual workflow observations, not a claim that
successful CI establishes business acceptance or physical fault independence. -/
namespace Ziokt.Release

-- BEGIN GENERATED VERIFIED GUARDS
abbrev ci_success (status : String) (conclusion : String) : Prop :=
  ((status = "completed") ∧ (conclusion = "success"))

abbrev same_revision (source : String) (compiler : String) : Prop :=
  (source = compiler)

-- END GENERATED VERIFIED GUARDS

inductive Check where
  | passed | failed | pending | cancelled
  deriving DecidableEq

def allPassed : List Check → Bool
  | [] => true
  | .passed :: tail => allPassed tail
  | _ :: _ => false

def publishable (checks : List Check) : Bool := !checks.isEmpty && allPassed checks

theorem empty_evidence_cannot_publish : publishable [] = false := rfl
theorem failed_check_cannot_publish (tail : List Check) : publishable (.failed :: tail) = false := rfl
theorem pending_check_cannot_publish (tail : List Check) : publishable (.pending :: tail) = false := rfl
theorem cancelled_check_cannot_publish (tail : List Check) : publishable (.cancelled :: tail) = false := rfl

theorem every_check_must_pass (checks : List Check) (h : allPassed checks = true)
    (check : Check) (member : check ∈ checks) : check = .passed := by
  induction checks with
  | nil => simp at member
  | cons head tail induction =>
    cases head <;> simp_all [allPassed]
    rcases member with equal | tailMember
    · exact equal
    · exact induction tailMember

def installable (source compiler : Nat) (checks : List Check) (digestMatched : Bool) : Prop :=
  source = compiler ∧ publishable checks = true ∧ digestMatched = true

theorem mismatched_compiler_cannot_install (source compiler : Nat) (checks : List Check)
    (digest : Bool) (h : source ≠ compiler) : ¬ installable source compiler checks digest := by
  intro accepted
  exact h accepted.1

theorem digest_failure_cannot_install (source compiler : Nat) (checks : List Check) :
    ¬ installable source compiler checks false := by
  intro accepted
  cases accepted.2.2

theorem publication_does_not_change_source (source compiler : Nat) (checks : List Check)
    (digest : Bool) (accepted : installable source compiler checks digest) : source = compiler := by
  exact accepted.1

theorem actual_pending_ci_cannot_publish (conclusion : String) :
    ¬ ci_success "queued" conclusion := by
  simp [ci_success]

theorem actual_failed_ci_cannot_publish : ¬ ci_success "completed" "failure" := by decide

theorem actual_other_compiler_revision_rejected (source compiler : String)
    (wrong : source ≠ compiler) : ¬ same_revision source compiler := by
  exact wrong

end Ziokt.Release
