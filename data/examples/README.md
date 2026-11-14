# Examples

Product files that show how to describe a product with a material added in `data/materials/`.
They are not part of the benchmark of the paper, and every mass is an illustrative assumption,
labelled as such. `experiments/new_materials_session.sh` uses them to check each added material
against openLCA.

| File | Material shown |
|---|---|
| `bag_in_box_3l.json` | corrugated board (with an LDPE bag) |
| `pp_bottle_1l.json` | polypropylene |
| `ps_cup_05l.json` | polystyrene |
| `eps_cup_03l.json` | expanded polystyrene |
| `pvc_bottle_1l.json` | PVC |
| `pla_cup_05l.json` | PLA |
| `steel_can_05l.json` | steel sheet (tinplate proxy) |
| `paper_bag_1l.json` | kraft paper (with an LDPE liner) |
| `carton_box_1l.json` | cartonboard (with an LDPE liner) |

Compare one with a benchmark product, for example
`python experiments/demo_cli.py --a data/examples/pp_bottle_1l.json --b pet_bottle_1l --region PT`.

## Products that are not containers

A product can also be described by inputs chosen from the openLCA database by process name
(`"exchanges"` in the product file): the stage, the exact process name, and the amount for one
product, or the smallest and the largest amount when it is not known. BRANCH then asks for the
exact amount only if it can change which product is better.

| File | What it shows |
|---|---|
| `cotton_bag.json`, `pp_bag.json` | two shopping bags, cotton and polypropylene: material, forming, sea freight and disposal, each as a range |

The amounts in these two files are illustrative assumptions, labelled as such. With openLCA open:

```bash
python experiments/extract_factors.py --update --specs data/examples/cotton_bag.json data/examples/pp_bag.json
python experiments/demo_cli.py --a data/examples/cotton_bag.json --b data/examples/pp_bag.json --region PT
```
