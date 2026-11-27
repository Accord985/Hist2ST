# Writing a Paper with LaTeX

This guide introduces the LaTeX workflow that may be helpful for this course. It is based on the week 4 lecture slides. 

## What LaTeX does

LaTeX is a document preparation system: you describe the document's structure and content, usually writing in `.tex`, and a compiler handles most of the appearance and generates a formatted PDF. It is useful for technical papers because section numbering, citations, equations, tables, and cross-references can update automatically.

## Templates

Rather than building from blank documents, this course asks us to follow specific templates used for publications for deliverables. 

- **Proposal:** [NSF Proposal Sample 2023](https://www.overleaf.com/latex/templates/nsf-proposal-sample-2023/nxjjtpzzkrnd), up to 10 pages.
- **Mid-project report:** [ACM Generic Journal Manuscript Template](https://www.overleaf.com/latex/templates/association-for-computing-machinery-acm-generic-journal-manuscript-template/yffvrvzbhhpt), up to 10 pages.
- **Final report:** [IEEE Conference Template](https://www.overleaf.com/latex/templates/ieee-conference-template/grfzhhncsfqn), up to 8 pages plus references/appendix.

Most templates contain a main source file called `main.tex` (or a similarly named file) and may also include section files, figures, a bibliography, and the class/style files. The main file is the document's entry point: it declares the class and packages, supplies the title information, includes the paper's sections, and ends the document. Overleaf compiles the selected main file to produce the PDF preview.

### *Optional: Support File Types, Explained*

*The support files defines what the template is like. For actual writing, you are mainly concerned with the `.tex` and `.bib` file. You do not need to edit the support files unless you know what you are doing.*

| *File Extension* |	*Full Name* |	*Purpose* |
| ------ | --- | --- |
| `.bst` | *BibTeX bibliography style* | *Controls citation data processing and reference-list formatting for BibTeX.* |
| `.bbx` | *BibLaTeX bibliography style* | *Controls the final reference-list layout.* |
| `.cbx` | *BibLaTeX citation style* | *Controls the format of citations in the document text.* |
| `.dbx` | *BibLaTeX data model* | *Controls allowed bibliography entry types and fields.* |
| `.cls` | *LaTeX document class* | *Controls document-wide layout, title elements, sections, and other formatting.* |
| `.sty` | *LaTeX package style* | *Adds reusable commands and features such as graphics, tables, or math support.* |

## Practical Writing workflow

Latex is just for formatting, so don't spend time worrying about latex before having the actual content. Look into the template `.tex` file for usage of **sections, tables, figures, equations, bibliography,** and **acknowledgements**. Check the template's documentation for detailed explanation. If you have trouble understanding the documentation, check the explanation for plain latex in the next section.  

#### Splitting the files

The handout recommends creating the section headings first and using one `.tex` file per section to make teamwork easier. For example, `main.tex` can include separate files like this:

```latex
\input{sections/introduction}
\input{sections/methods}
\input{sections/results}
\input{sections/discussion}
```

Each included file contains just that section's content, without another `\documentclass` or `\begin{document}`. `\input{file}` inserts another `.tex` file at that point and is commonly used for sections. Keep compiling the project while writing, so problems are easy to find.

*PS: `\include{file}` has similar behavior as `\input` but it starts a new page and uses auxiliary files for that part, so it is more suited to larger, independent divisions such as book chapters.*

## Classic Latex

What follows is a demonstration for creating the common components in plain latex. **The templates might use different commands for these things.**

### `main.tex`

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



### Sections and subsections

Use `\section{Section title}` to add a numbered top-level section and `\subsection{Subsection title}` to add a numbered subsection. Place text and formatting commands below the corresponding heading:

```latex
\section{Introduction}
This paragraph describes the introduction.

\subsection{Background}
This paragraph describes the background.

\subsection{Research Question}
This paragraph states the research question.
```

Use `*` after the command name, such as `\section*{Conclusion}`, for an unnumbered section.

### Tables

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

Refer to it in the text with `Table~\ref{tab:performance}`. The `~` represents a space and keeps “Table” and its number together on a line. Place `\label` after `\caption`, so the label captures the table's number. Keep the caption informative and define abbreviations. 

Column alignment in `{lrr}` means left, right, right. Use `&` between cells and `\\` to end a row. Escape special characters in ordinary text: for example, write `50\%` for 50 percent and `A\_B` for an underscore.

### Figures

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

### Equations and inline math

Use `$...$` for a short mathematical expression within a sentence. Use an equation environment for a displayed, numbered equation:

```latex
\begin{equation}
  \mathrm{MAE} = \frac{1}{n}\sum_{i=1}^{n} |y_i - \hat{y}_i|
  \label{eq:mae}
\end{equation}
```

Refer to it as `Equation~\ref{eq:mae}`.

### Citations and bibliography

Keep references in a `.bib` file when the template supports BibTeX or BibLaTeX. Reference managers such as Zotero can export your references as those formats. 

A bibliography record has a citation key, such as `smith2024`, which you cite in the text using the template's expected command (for example, `\cite{smith2024}`). 

### Lists, labels, and common syntax

Bulleted lists use `itemize`; numbered lists use `enumerate`:

```latex
\begin{itemize}
  \item First point.
  \item Second point.
\end{itemize}
```

Use labels and `\ref` for sections, figures, tables, and equations instead of typing their numbers by hand. LaTeX updates the numbering when content moves. After adding references, compile again if the preview shows `??`; cross-references can take another compilation pass to resolve.

Common text commands include `\textbf{bold}` and `\emph{emphasis}`. In ordinary text, `%`, `&`, `$`, `#`, `_`, `{`, and `}` have special meanings, so escape them with a backslash when you mean the character itself (for example, `\&`). LaTeX commands are case-sensitive.

### Helpful Links

- [Overleaf Learn LaTeX](https://www.overleaf.com/learn): beginner material and guides for document structure, figures, tables, math, and bibliography management.
- [Tables in LaTeX](https://www.overleaf.com/learn/latex/Tables): more table examples, including longer tables.
- [Overleaf template gallery](https://www.overleaf.com/latex/templates): templates for academic papers, journals, reports, and other documents.
