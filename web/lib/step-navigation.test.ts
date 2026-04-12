import assert from "node:assert/strict";
import test from "node:test";

const { canSelectWizardStep } = await import(new URL("./step-navigation.ts", import.meta.url).href);

test("allows backward step jumps without re-validating the current step", () => {
  let validationCalls = 0;

  assert.equal(
    canSelectWizardStep({
      currentStep: 3,
      targetStep: 2,
      lastSelectableStep: 5,
      validateCurrentStep: () => {
        validationCalls += 1;
        return false;
      },
    }),
    true,
  );

  assert.equal(validationCalls, 0);
});

test("blocks forward step jumps when current-step validation fails", () => {
  let validationCalls = 0;

  assert.equal(
    canSelectWizardStep({
      currentStep: 3,
      targetStep: 4,
      lastSelectableStep: 5,
      validateCurrentStep: () => {
        validationCalls += 1;
        return false;
      },
    }),
    false,
  );

  assert.equal(validationCalls, 1);
});

test("requires the injury overwrite gate before allowing a forward step jump", () => {
  const injuryOverwriteAcknowledged = false;
  const injuryMismatchExists = true;

  assert.equal(
    canSelectWizardStep({
      currentStep: 3,
      targetStep: 4,
      lastSelectableStep: 5,
      validateCurrentStep: () => !(injuryMismatchExists && !injuryOverwriteAcknowledged),
    }),
    false,
  );
});

test("rejects review-step and out-of-range pill targets", () => {
  assert.equal(
    canSelectWizardStep({
      currentStep: 2,
      targetStep: 5,
      lastSelectableStep: 5,
      validateCurrentStep: () => true,
    }),
    false,
  );

  assert.equal(
    canSelectWizardStep({
      currentStep: 2,
      targetStep: -1,
      lastSelectableStep: 5,
      validateCurrentStep: () => true,
    }),
    false,
  );
});

test("allows selecting review step when caller expands the selectable boundary", () => {
  assert.equal(
    canSelectWizardStep({
      currentStep: 2,
      targetStep: 5,
      lastSelectableStep: 6,
      validateCurrentStep: () => true,
    }),
    true,
  );
});
