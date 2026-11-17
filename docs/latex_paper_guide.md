# Writing a Paper with LaTeX

This guide introduces the LaTeX workflow used in the course handout. It covers getting started, understanding `main.tex`, organizing a paper by sections, and adding common elements such as figures, tables, equations, and references.

## What LaTeX does

LaTeX is a document preparation system: you write plain-text source files, usually ending in `.tex`, and a compiler turns them into a formatted PDF. You describe the document's structure and content; the class and template handle most of its appearance. It is useful for technical papers because section numbering, citations, equations, tables, and cross-references can update automatically.

The Week 4 handout frames LaTeX as one part of a reproducible project workflow. That connection matters when writing a paper: keep the source, figures, and bibliography organized in Git, and report enough experimental details for someone else to understand or reproduce the results.

## Start from a template

For a course deliverable or publication, begin with the required template rather than a blank document. The class file (`.cls`) controls document-wide formatting, and packages (`.sty` files) add features. A bibliography style (`.bst`) controls reference formatting. Keep your writing in the `.tex` source files; do not edit the class or style files or change margins and fonts to get around page limits.

The handout lists these course templates on Overleaf:

- **Proposal:** [NSF Proposal Sample 2023](https://www.overleaf.com/latex/templates/nsf-proposal-sample-2023/nxjjtpzzkrnd), up to 10 pages.
- **Mid-project report:** [ACM Generic Journal Manuscript Template](https://www.overleaf.com/latex/templates/association-for-computing-machinery-acm-generic-journal-manuscript-template/yffvrvzbhhpt), up to 10 pages.
- **Final report:** [IEEE Conference Template](https://www.overleaf.com/latex/templates/ieee-conference-template/grfzhhncsfqn), up to 8 pages plus references/appendix.

The page limits above are those shown in the handout; follow the latest course instructions if they differ. On Overleaf, open a template and choose **Open as Template**, then share the project with teammates. For a journal or conference submission, use that venue's current official template. Overleaf's [template gallery](https://www.overleaf.com/latex/templates) has other paper and report templates.

## The basic project and `main.tex`

Most templates contain a main source file called `main.tex` (or a similarly named file) and may also include section files, figures, a bibliography, and the class/style files. The main file is the document's entry point: it declares the class and packages, supplies the title information, includes the paper's sections, and ends the document. Overleaf compiles the selected main file to produce the PDF preview.

A small example shows the structure. In a supplied template, keep its existing `\documentclass` and required setup rather than copying this example over it.

```latex
\documentclass{article} % A template may use a journal or conference class instead.
\usepackage{graphicx}   % Include image files.
\usepackage{booktabs}  % Clean table rules.

\title{A Clear, Specific Paper Title}
\author{Author One \and Author Two}
\date{\today}

\begin{document}
\maketitle

\begin{abstract}
Briefly state the problem, approach, main result, and conclusion.
\end{abstract}

\section{Introduction}
Explain the problem and why it matters.

\section{Methods}
Describe the data, split, model, and evaluation.

\section{Results}
Report the findings and refer to figures and tables by label.

\section{Discussion}
Interpret the results and describe limitations.

\end{document}
```

The commands beginning with a backslash are instructions. For example, `\section{Results}` creates a numbered heading, while `\begin{abstract}` and `\end{abstract}` mark the start and end of an abstract. A blank line starts a new paragraph; a single line break in the source usually does not start a new paragraph.

### Split a longer paper into files

The handout recommends creating the section headings first and using one `.tex` file per section to make teamwork easier. For example, `main.tex` can include separate files like this:

```latex
\input{sections/introduction}
\input{sections/methods}
\input{sections/results}
\input{sections/discussion}
```

Each included file contains just that section's content, without another `\documentclass` or `\begin{document}`. Templates may use `\include` or another arrangement; follow their existing structure. Keep the project compiling while writing, so problems are easy to find.

## A paper's sections

The exact headings depend on the assignment and field. A common empirical paper uses the following structure; treat it as a starting point and adapt it to the template and rubric.

1. **Title and authors:** State the topic clearly and list authors and affiliations in the template's format.
2. **Abstract:** In a short standalone summary, give the problem, approach, most important result, and takeaway. Write it after the paper is stable.
3. **Introduction:** Explain the problem and its importance, summarize relevant prior work, identify the gap or question, and preview your contribution and paper organization.
4. **Related Work** (sometimes part of the Introduction): Compare relevant approaches and explain how your work fits. Cite and verify the sources you discuss.
5. **Data and Methods:** Describe the data source and inclusion criteria; preprocessing; experimental design and split unit; model or baseline; training details; metrics; and statistical comparisons. Make choices specific enough to interpret and reproduce the experiment.
6. **Results:** Report what happened, using tables and figures where they help. State the relevant sample sizes, comparisons, and uncertainty. Keep interpretation tied to evidence.
7. **Discussion:** Explain what the results mean, compare them with prior work, note limitations and possible confounders, and describe useful next steps.
8. **Conclusion:** Summarize the main finding and its practical or scientific implication without introducing new evidence.
9. **References:** Include sources cited in the paper, formatted by the template. Check each reference against the original source.
10. **Appendix** (if allowed): Put supplementary details, extra results, or derivations here. Check whether appendices count toward the page limit.

For a project paper, reproducibility details often belong in Methods or a supplement: the exact train/validation/test split, preprocessing, random seeds, model settings, software environment, and the code version. The handout's checklist also calls out logs, outputs, and the final metric-calculation script. In Git, commit the paper source and reasonable-sized figures; follow the project rules for large data, model weights, and generated files.

## Tables

Use `tabular` to arrange rows and columns. The outer `table` environment lets LaTeX place the table where it fits, add a caption, number it, and make it referenceable. The template may load `booktabs`; use its horizontal rules for a clean table and avoid drawing a box around every cell.

```latex
\begin{table}[t]
  \centering
  \caption{Example performance on the held-out test set.}
  \label{tab:performance}
  \begin{tabular}{lrr}
    \toprule
    Method & MAE (lower is better) & $R^2$ (higher is better) \\
    \midrule
    Baseline & 0.42 & 0.31 \\
    Proposed & 0.35 & 0.46 \\
    \bottomrule
  \end{tabular}
\end{table}
```

Refer to it in the text with `Table~\ref{tab:performance}`. The `~` keeps “Table” and its number together on a line. Place `\label` after `\caption`, so the label captures the table's number. Keep the caption informative, define abbreviations, and include units or the direction of better performance. A table should support a point made in the text; do not make readers guess what comparison matters.

Column alignment in `{lrr}` means left, right, right. Use `&` between cells and `\\` to end a row. Escape special characters in ordinary text: for example, write `50\%` for 50 percent and `A\_B` for an underscore.

## Figures

Put image files in an organized folder such as `figures/`. The handout recommends adding figures early and using vector PDF for plots where possible; vector graphics stay sharp when enlarged. Use PNG or JPEG for raster images such as photographs. Include `\usepackage{graphicx}` if the template does not already load it.

```latex
\begin{figure}[t]
  \centering
  \includegraphics[width=0.85\linewidth]{figures/workflow.pdf}
  \caption{Overview of the data and evaluation workflow.}
  \label{fig:workflow}
\end{figure}
```

Refer to it in the text with `Figure~\ref{fig:workflow}`. Explain the main result in the caption, define symbols and abbreviations, and make labels readable at the final paper size. Figure placement options like `[t]` are suggestions to LaTeX, not fixed coordinates; it may move a figure to improve page layout.

## Equations and inline math

Use `$...$` for a short mathematical expression within a sentence. Use an equation environment for a displayed, numbered equation:

```latex
\begin{equation}
  \mathrm{MAE} = \frac{1}{n}\sum_{i=1}^{n} |y_i - \hat{y}_i|
  \label{eq:mae}
\end{equation}
```

Refer to it as `Equation~\ref{eq:mae}`. Explain each symbol in the surrounding prose. Use a template's existing math packages and notation style when available.

## Citations and bibliography

Keep references in a `.bib` file when the template supports BibTeX or BibLaTeX. A bibliography record has a citation key, such as `smith2024`, which you cite in the text using the template's expected command (for example, `\cite{smith2024}`). The template determines how citations and the reference list look, so use its bibliography commands and style rather than mixing systems.

Reference managers such as Zotero can export BibTeX entries. As the handout advises, verify each citation yourself: check the title, authors, year, venue, and that the source actually supports the statement. A successful compile only means the citation key was found; it does not verify the reference's accuracy.

## Lists, labels, and common syntax

Bulleted lists use `itemize`; numbered lists use `enumerate`:

```latex
\begin{itemize}
  \item First point.
  \item Second point.
\end{itemize}
```

Use labels and `\ref` for sections, figures, tables, and equations instead of typing their numbers by hand. LaTeX updates the numbering when content moves. After adding references, compile again if the preview shows `??`; cross-references can take another compilation pass to resolve.

Common text commands include `\textbf{bold}` and `\emph{emphasis}`. In ordinary text, `%`, `&`, `$`, `#`, `_`, `{`, and `}` have special meanings, so escape them with a backslash when you mean the character itself (for example, `\&`). LaTeX commands are case-sensitive.

## A practical writing workflow

1. Open the required course or venue template and confirm its main file and instructions.
2. Create the paper's section headings and labels first. Divide longer sections into separate files if teammates will write in parallel.
3. Draft the methods and experimental design clearly. Decide the split unit, baseline, metrics, and main comparison before interpreting results.
4. Add tables and figures as soon as results exist. Refer to each one in the text and explain the message it supports.
5. Maintain references in the bibliography file and verify the original sources.
6. Compile often. Fix errors near where they appear; a missing brace or unmatched `\begin`/`\end` can cause many later errors.
7. Check the rendered PDF for missing figures, unreadable labels, awkward page breaks, unresolved references, and template-specific requirements.
8. Save source, bibliography, and figure files in Git. Make small commits and keep the project reproducible; do not commit secrets, restricted data, or unapproved large files.

For cluster work, the LaTeX source can remain in the Git repository while experiments run on the cluster. Record the code version and experiment settings used to make reported results. The paper should describe the tested procedure and results, not just the intended plan.

## Learn and troubleshoot

- [Overleaf Learn LaTeX](https://www.overleaf.com/learn): beginner material and guides for document structure, figures, tables, math, and bibliography management.
- [Tables in LaTeX](https://www.overleaf.com/learn/latex/Tables): more table examples, including longer tables.
- [Overleaf template gallery](https://www.overleaf.com/latex/templates): templates for academic papers, journals, reports, and other documents.

When an error appears, read the first error in the compile log and inspect the nearby source. Check for a missing `}`, unmatched environment, misspelled filename, absent image, or unknown citation key. Compile again after making a focused fix.
