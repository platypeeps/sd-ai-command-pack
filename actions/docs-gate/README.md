# The mechanical half of the documentation review

`actions/docs-gate` runs `sd-research-kit` against the repository the workflow is checked out in.
It reads that checkout, writes nothing to it, and requests no reviewer.
By default it runs `review` and then `checklinks`.

Set `verbs` to choose others, space separated and in order.
`review`, `checklinks`, `pins` and `conventions` are accepted.
`render` is refused: it writes, and this action promises it does not.
An unknown verb stops the run rather than being skipped, because a gate that silently ran nothing is the failure this action exists to avoid.

Every named verb runs even when an earlier one fails, so one report names every problem instead of only the first.
The action exits non-zero if any of them did.

## Why an action rather than a checkout

The kit lives beside this action, outside the workspace, and needs no `PATH` entry: `sd-research-kit` resolves its own helpers from the directory it sits in, and resolves the repository it checks from the current working directory.

That placement is the point for `checklinks`, which walks the tree it is standing in.
A consumer that checked this pack out into its own workspace had to move the checkout aside afterwards, or the pack's own markdown landed in the consumer's link report.

## Use

```yaml
- uses: actions/checkout@v4
- uses: platypeeps/sd-ai-command-pack/actions/docs-gate@<commit>
```

`review` runs `sd-docs-lint` over `docs/work/` when that directory exists, so a repository following both `sd-research-repo` and `sd-plan` is checked against both.
A repository with no `docs/work/` never pays for it.
