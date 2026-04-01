type StepSelectionGuardOptions = {
  currentStep: number;
  targetStep: number;
  lastSelectableStep: number;
  validateCurrentStep: () => boolean;
};

export function canSelectWizardStep({
  currentStep,
  targetStep,
  lastSelectableStep,
  validateCurrentStep,
}: StepSelectionGuardOptions): boolean {
  if (targetStep < 0 || targetStep >= lastSelectableStep) {
    return false;
  }
  if (targetStep <= currentStep) {
    return true;
  }
  return validateCurrentStep();
}
