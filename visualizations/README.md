# Thesis visualization pack

This pack contains thesis-ready figures for **Enhancing Continuous Testing in DevOps and CI/CD Pipelines Using Large Language Models**. Each figure is supplied as:

- `SVG` - editable vector artwork (preferred for revision)
- `PDF` - vector format for final typesetting
- `PNG` - 300-DPI raster format for Microsoft Word

The suggested numbering is provisional. Renumber each figure to match its final chapter position. Per the supplied thesis guideline, center every figure, use a 10-point sentence-case caption, include the chapter in the figure number, and refer to every figure by number in the body text.

## Figures and captions

### 1. figure_1_1_research_conceptual_model

- **Suggested placement:** Chapter 1 - Introduction
- **Caption:** Conceptual model of LLM-enhanced continuous testing.
- **Source line:** Source: Developed by the researcher from the proposal problem statement and objectives.
- **Suggested interpretation:** The framework is expected to convert known continuous-testing bottlenecks into measurable effectiveness, efficiency and reliability outcomes, subject to governance safeguards.
- **Files:** [figure_1_1_research_conceptual_model.png](output/figure_1_1_research_conceptual_model.png) | [figure_1_1_research_conceptual_model.svg](output/figure_1_1_research_conceptual_model.svg) | [figure_1_1_research_conceptual_model.pdf](output/figure_1_1_research_conceptual_model.pdf)

### 2. figure_1_2_rq_objective_mapping

- **Suggested placement:** Chapter 1 - Introduction
- **Caption:** Mapping of the research questions, objectives and evaluation evidence.
- **Source line:** Source: Developed by the researcher from the approved research proposal.
- **Files:** [figure_1_2_rq_objective_mapping.png](output/figure_1_2_rq_objective_mapping.png) | [figure_1_2_rq_objective_mapping.svg](output/figure_1_2_rq_objective_mapping.svg) | [figure_1_2_rq_objective_mapping.pdf](output/figure_1_2_rq_objective_mapping.pdf)

### 3. figure_2_1_evolution_intelligent_testing

- **Suggested placement:** Chapter 2 - Literature Review
- **Caption:** Evolution from traditional test automation to agentic LLM-driven continuous testing.
- **Source line:** Source: Synthesized by the researcher from the literature reviewed in the proposal.
- **Files:** [figure_2_1_evolution_intelligent_testing.png](output/figure_2_1_evolution_intelligent_testing.png) | [figure_2_1_evolution_intelligent_testing.svg](output/figure_2_1_evolution_intelligent_testing.svg) | [figure_2_1_evolution_intelligent_testing.pdf](output/figure_2_1_evolution_intelligent_testing.pdf)

### 4. figure_2_2_research_gap_contribution

- **Suggested placement:** Chapter 2 - Literature Review
- **Caption:** Research gap addressed by the proposed LLM-CTF framework.
- **Source line:** Source: Developed by the researcher from the research-gap analysis in the proposal.
- **Files:** [figure_2_2_research_gap_contribution.png](output/figure_2_2_research_gap_contribution.png) | [figure_2_2_research_gap_contribution.svg](output/figure_2_2_research_gap_contribution.svg) | [figure_2_2_research_gap_contribution.pdf](output/figure_2_2_research_gap_contribution.pdf)

### 5. figure_3_1_dsr_methodology_cycle

- **Suggested placement:** Chapter 3 - Methodology
- **Caption:** Design Science Research cycle used to develop and evaluate the LLM-CTF artifact.
- **Source line:** Source: Adapted by the researcher from the DSR approach specified in the proposal.
- **Files:** [figure_3_1_dsr_methodology_cycle.png](output/figure_3_1_dsr_methodology_cycle.png) | [figure_3_1_dsr_methodology_cycle.svg](output/figure_3_1_dsr_methodology_cycle.svg) | [figure_3_1_dsr_methodology_cycle.pdf](output/figure_3_1_dsr_methodology_cycle.pdf)

### 6. figure_3_2_llm_ctf_architecture

- **Suggested placement:** Chapter 3 - Methodology / System Design
- **Caption:** Architecture of the implemented LLM-CTF prototype.
- **Source line:** Source: Developed by the researcher from main.py, the agent modules and the GitHub Actions workflow.
- **Files:** [figure_3_2_llm_ctf_architecture.png](output/figure_3_2_llm_ctf_architecture.png) | [figure_3_2_llm_ctf_architecture.svg](output/figure_3_2_llm_ctf_architecture.svg) | [figure_3_2_llm_ctf_architecture.pdf](output/figure_3_2_llm_ctf_architecture.pdf)

### 7. figure_3_3_cicd_integration_workflow

- **Suggested placement:** Chapter 3 - Methodology / Implementation
- **Caption:** CI/CD integration workflow used by the implemented prototype.
- **Source line:** Source: Developed by the researcher from .github/workflows/ci-cd.yaml.
- **Files:** [figure_3_3_cicd_integration_workflow.png](output/figure_3_3_cicd_integration_workflow.png) | [figure_3_3_cicd_integration_workflow.svg](output/figure_3_3_cicd_integration_workflow.svg) | [figure_3_3_cicd_integration_workflow.pdf](output/figure_3_3_cicd_integration_workflow.pdf)

### 8. figure_3_4_testgen_agent_workflow

- **Suggested placement:** Chapter 3 - Methodology / Implementation
- **Caption:** Operational workflow of the TestGenAgent.
- **Source line:** Source: Developed by the researcher from tests_generated/generator.py.
- **Files:** [figure_3_4_testgen_agent_workflow.png](output/figure_3_4_testgen_agent_workflow.png) | [figure_3_4_testgen_agent_workflow.svg](output/figure_3_4_testgen_agent_workflow.svg) | [figure_3_4_testgen_agent_workflow.pdf](output/figure_3_4_testgen_agent_workflow.pdf)

### 9. figure_3_5_testselect_agent_workflow

- **Suggested placement:** Chapter 3 - Methodology / Implementation
- **Caption:** Predictive test-selection workflow of the TestSelectAgent.
- **Source line:** Source: Developed by the researcher from tests_selecter/selecter.py.
- **Files:** [figure_3_5_testselect_agent_workflow.png](output/figure_3_5_testselect_agent_workflow.png) | [figure_3_5_testselect_agent_workflow.svg](output/figure_3_5_testselect_agent_workflow.svg) | [figure_3_5_testselect_agent_workflow.pdf](output/figure_3_5_testselect_agent_workflow.pdf)

### 10. figure_3_6_self_healing_decision_flow

- **Suggested placement:** Chapter 3 - Methodology / Implementation
- **Caption:** Guarded autonomous self-healing transaction for failed selected tests.
- **Source line:** Source: Developed by the researcher from tests_selecter/selecter.py and tests_selecter/self_healing.py.
- **Suggested interpretation:** The implementation combines constrained LLM output with deterministic structural policy checks, repeated execution, transaction-wide rollback and persistent audit evidence.
- **Files:** [figure_3_6_self_healing_decision_flow.png](output/figure_3_6_self_healing_decision_flow.png) | [figure_3_6_self_healing_decision_flow.svg](output/figure_3_6_self_healing_decision_flow.svg) | [figure_3_6_self_healing_decision_flow.pdf](output/figure_3_6_self_healing_decision_flow.pdf)

### 11. figure_3_7_experimental_design

- **Suggested placement:** Chapter 3 - Methodology / Evaluation Design
- **Caption:** Experimental design for comparing traditional and agentic test execution strategies.
- **Source line:** Source: Developed by the researcher from tests_selecter/comparison_report.py and the CI workflow.
- **Files:** [figure_3_7_experimental_design.png](output/figure_3_7_experimental_design.png) | [figure_3_7_experimental_design.svg](output/figure_3_7_experimental_design.svg) | [figure_3_7_experimental_design.pdf](output/figure_3_7_experimental_design.pdf)

### 12. figure_3_8_evaluation_metrics_framework

- **Suggested placement:** Chapter 3 - Methodology / Evaluation Design
- **Caption:** Metrics framework for evaluating LLM-CTF effectiveness, efficiency, reliability and governance.
- **Source line:** Source: Developed by the researcher from RO2 and the proposal's stated evaluation criteria.
- **Files:** [figure_3_8_evaluation_metrics_framework.png](output/figure_3_8_evaluation_metrics_framework.png) | [figure_3_8_evaluation_metrics_framework.svg](output/figure_3_8_evaluation_metrics_framework.svg) | [figure_3_8_evaluation_metrics_framework.pdf](output/figure_3_8_evaluation_metrics_framework.pdf)

### 13. figure_4_1_tests_executed_comparison

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Number of tests executed by the traditional and agentic strategies.
- **Source line:** Source: Calculated from test-results.csv and reports/test_results.csv.
- **Suggested interpretation:** The predictive selector executed 16 of 78 application tests, reducing the executed test count by 79.5% in this run.
- **Files:** [figure_4_1_tests_executed_comparison.png](output/figure_4_1_tests_executed_comparison.png) | [figure_4_1_tests_executed_comparison.svg](output/figure_4_1_tests_executed_comparison.svg) | [figure_4_1_tests_executed_comparison.pdf](output/figure_4_1_tests_executed_comparison.pdf)

### 14. figure_4_2_execution_time_comparison

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Measured wall time of the traditional full-batch and agentic selected-test strategies.
- **Source line:** Source: Calculated from reports/comparison_report.csv.
- **Suggested interpretation:** The agentic selected-test workflow took 14.278 seconds versus 63.770 seconds for the full application batch, a 77.6% reduction while retaining 16 impacted tests. This excludes the separate final CI safety gate; no repair was triggered because all selected tests passed.
- **Files:** [figure_4_2_execution_time_comparison.png](output/figure_4_2_execution_time_comparison.png) | [figure_4_2_execution_time_comparison.svg](output/figure_4_2_execution_time_comparison.svg) | [figure_4_2_execution_time_comparison.pdf](output/figure_4_2_execution_time_comparison.pdf)

### 15. figure_4_3_predictive_selection_outcome

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Distribution of selected and skipped tests in the predictive-selection run.
- **Source line:** Source: Calculated from test-results.csv and reports/test_results.csv.
- **Files:** [figure_4_3_predictive_selection_outcome.png](output/figure_4_3_predictive_selection_outcome.png) | [figure_4_3_predictive_selection_outcome.svg](output/figure_4_3_predictive_selection_outcome.svg) | [figure_4_3_predictive_selection_outcome.pdf](output/figure_4_3_predictive_selection_outcome.pdf)

### 16. figure_4_4_paired_test_durations

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Paired duration comparison for tests executed under both strategies.
- **Source line:** Source: Calculated by matching test IDs in test-results.csv and reports/test_results.csv.
- **Suggested interpretation:** The same 16 tests are paired by node ID. The selected-workflow speed difference primarily comes from executing fewer tests and batching them in one pytest process.
- **Files:** [figure_4_4_paired_test_durations.png](output/figure_4_4_paired_test_durations.png) | [figure_4_4_paired_test_durations.svg](output/figure_4_4_paired_test_durations.svg) | [figure_4_4_paired_test_durations.pdf](output/figure_4_4_paired_test_durations.pdf)

### 17. figure_4_5_generated_tests_by_capability

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Distribution of LLM-generated tests across API capability groups.
- **Source line:** Source: Calculated from reports/generated_test_results.csv; categories were assigned from test identifiers.
- **Suggested interpretation:** The generator result contains 13 tests, of which 13 passed, covering users, posts, performance, observability and test-hook capabilities.
- **Files:** [figure_4_5_generated_tests_by_capability.png](output/figure_4_5_generated_tests_by_capability.png) | [figure_4_5_generated_tests_by_capability.svg](output/figure_4_5_generated_tests_by_capability.svg) | [figure_4_5_generated_tests_by_capability.pdf](output/figure_4_5_generated_tests_by_capability.pdf)

### 18. figure_4_6_complete_suite_composition

- **Suggested placement:** Chapter 4 - Results and Findings
- **Caption:** Composition of the application-test inventory by test origin.
- **Source line:** Source: Calculated from test-results.csv using the test module path.
- **Suggested interpretation:** The application experiment contained 65 handwritten tests and 13 generated tests; repair-engine guardrail tests are reported separately.
- **Files:** [figure_4_6_complete_suite_composition.png](output/figure_4_6_complete_suite_composition.png) | [figure_4_6_complete_suite_composition.svg](output/figure_4_6_complete_suite_composition.svg) | [figure_4_6_complete_suite_composition.pdf](output/figure_4_6_complete_suite_composition.pdf)

## Evidence boundaries

Figures 1.1-3.8 are conceptual, methodological, or implementation diagrams. Figures 4.1-4.6 are computed from the current workspace CSV files and describe one prototype run; they must not be generalized as final research findings without repeated experiments, uncertainty estimates, and controlled replications. Figure 4.2 compares the 78-test application batch with the selector/decision/16-test batch only; the separate 106-test post-healing CI safety gate is excluded from that efficiency comparison. The observed selected batch had no failures, so repair correctness is supported by deterministic guardrail tests rather than a live repair outcome in this run.

## Regeneration

Run `python visualizations/generate_visualizations.py` from the repository root after replacing the CSV reports with updated experimental results.
