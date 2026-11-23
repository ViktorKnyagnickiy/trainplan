"""Статистична обробка результатів експериментів і побудова рисунків для розділу 4."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker

RES = Path(__file__).parent / 'results'
FIG = Path(__file__).parent / 'figures'
FIG.mkdir(exist_ok=True)
plt.rcParams.update({'axes.formatter.use_locale': False, 'font.family': 'DejaVu Serif', 'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.grid': True, 'grid.color': '#e4e4e0', 'grid.linewidth': 0.6,
                     'axes.axisbelow': True, 'axes.edgecolor': '#52514e', 'xtick.color': '#52514e',
                     'ytick.color': '#52514e', 'axes.labelcolor': '#0b0b0b'})
COL = {'CSP': '#2a78d6', 'Відпал': '#8a5cc7', 'Жадібний': '#eb6834', 'Шаблон': '#1baf7a', 'LLM': '#eda100'}
HATCH = {'CSP': '', 'Відпал': '\\\\', 'Жадібний': '//', 'Шаблон': '..', 'LLM': 'xx'}
LABEL = {'CSP': 'Запропонована модель', 'Відпал': 'Імітація відпалу', 'Жадібний': 'Жадібна евристика', 'Шаблон': 'Шаблон', 'LLM': 'LLM'}
OUT = {}


def rank_biserial(x, y):
    d = np.asarray(x) - np.asarray(y)
    d = d[d != 0]
    if not len(d):
        return 0.0
    r = stats.rankdata(np.abs(d))
    return (r[d > 0].sum() - r[d < 0].sum()) / r.sum()


def holm(pvals):
    order = np.argsort(pvals)
    adj, m, prev = np.empty(len(pvals)), len(pvals), 0
    for k, i in enumerate(order):
        prev = max(prev, min(1, (m - k) * pvals[i]))
        adj[i] = prev
    return adj


def summary(df):
    g = df.groupby('method')
    s = pd.DataFrame({
        'n': g.size(),
        'feasible': g.apply(lambda x: (x.status.isin(['optimal', 'feasible']) & x.K1.notna()).mean()),
        'K1_zero': g.apply(lambda x: (x.K1 == 0).mean()),
        'K1_mean': g.K1.mean(),
        'K2_mean': g.K2.mean(), 'K2_median': g.K2.median(),
        'in_range': g.K2_groups_in_range.mean(),
        'K3': g.K3.mean(),
        'K4_ok': g.apply(lambda x: ((x.K4 >= 0.8) & (x.K4 <= 1.25)).mean()),
        'K5': g.K5.mean(),
        'rt_median': g.runtime.median(), 'rt_p95': g.runtime.quantile(0.95), 'rt_max': g.runtime.max(),
    })
    return s


def main():
    df = pd.read_csv(RES / 'compare.csv')
    df['method'] = df['method'].replace({'CSP': 'CSP', 'Шаблон': 'Шаблон'})
    ok = df[df.K1.notna()]
    OUT['n_profiles'] = int(df.profile.nunique())
    csp = df[df.method == 'CSP']
    OUT['csp_status'] = csp.status.value_counts().to_dict()
    OUT['csp_gap_mean_feasible'] = float(csp[csp.status == 'feasible'].gap.mean()) if (csp.status == 'feasible').any() else None
    OUT['csp_n_vars'] = [int(csp.n_vars.min()), int(csp.n_vars.max())]
    OUT['csp_n_cons'] = [int(csp.n_cons.min()), int(csp.n_cons.max())]
    OUT['summary'] = summary(df).round(4).reset_index().to_dict('records')
    # парні порівняння на профілях, допустимих для всіх методів
    piv = ok.pivot_table(index='profile', columns='method', values=['K2', 'K3', 'K5', 'K4_log'])
    piv = piv.dropna()
    OUT['n_paired'] = int(len(piv))
    tests, pv = [], []
    for metric, better in [('K2', 'less'), ('K3', 'greater'), ('K4_log', 'less'), ('K5', 'greater')]:
        for other in ('Відпал', 'Жадібний', 'Шаблон'):
            a, b = piv[(metric, 'CSP')], piv[(metric, other)]
            try:
                w = stats.wilcoxon(a, b, alternative=better, zero_method='wilcox')
                p = float(w.pvalue)
            except ValueError:
                p = 1.0
            tests.append(dict(metric=metric, other=other, csp_mean=float(a.mean()), other_mean=float(b.mean()),
                              r_rb=float(rank_biserial(a, b)), wins=int((a < b).sum() if better == 'less' else (a > b).sum()),
                              ties=int((a == b).sum()), losses=int((a > b).sum() if better == 'less' else (a < b).sum())))
            pv.append(p)
    for t, p, pa in zip(tests, pv, holm(np.array(pv))):
        t['p'] = p; t['p_holm'] = float(pa)
    OUT['wilcoxon'] = tests
    # за типом обладнання
    OUT['by_equip'] = ok.groupby(['equip', 'method']).K2.mean().round(4).unstack().to_dict()
    OUT['by_days'] = ok[ok.method == 'CSP'].groupby('n_days').runtime.median().round(3).to_dict()
    OUT['csp_violations'] = int(ok[ok.method == 'CSP'].K1.sum())
    OUT['viol_types'] = ok.groupby('method')[['viol_equipment', 'viol_contra', 'viol_level', 'viol_duration',
                                              'viol_recovery']].sum().astype(int).to_dict('index')
    OUT['K2_zero_share'] = ok.groupby('method').apply(lambda x: (x.K2 == 0).mean()).round(4).to_dict()

    # ---------- підвибірка LLM
    llm = pd.read_csv(RES / 'llm.csv')
    sub = df[df.profile.isin(llm.profile) & (df.method != 'Відпал')]
    both = pd.concat([sub, llm[sub.columns.intersection(llm.columns)]], ignore_index=True)
    OUT['llm_summary'] = summary(both).round(4).reset_index().to_dict('records')
    OUT['llm_viol_profiles'] = int((llm.K1 > 0).sum())
    OUT['llm_viol_types'] = llm[['viol_equipment', 'viol_contra', 'viol_level', 'viol_duration', 'viol_recovery']].sum().astype(int).to_dict()
    OUT['llm_days_unused'] = int((llm.days_used < llm.n_days).sum())
    OUT['llm_format_errors'] = int(llm.unknown_id.sum() + llm.wrong_day.sum())
    p4 = both.pivot_table(index='profile', columns='method', values='K2').dropna()
    fr = stats.friedmanchisquare(*[p4[m] for m in p4.columns])
    OUT['friedman_K2'] = dict(stat=float(fr.statistic), p=float(fr.pvalue), n=int(len(p4)),
                              mean_ranks=p4.rank(axis=1).mean().round(2).to_dict())
    w = stats.wilcoxon(p4['CSP'], p4['LLM'], alternative='less')
    OUT['csp_vs_llm_K2'] = dict(p=float(w.pvalue), r_rb=float(rank_biserial(p4['CSP'], p4['LLM'])),
                                csp_mean=float(p4['CSP'].mean()), llm_mean=float(p4['LLM'].mean()),
                                wins=int((p4['CSP'] < p4['LLM']).sum()), ties=int((p4['CSP'] == p4['LLM']).sum()))
    OUT['llm_rows'] = llm[['profile', 'goal', 'level', 'n_days', 'days_used', 'tmax', 'equip', 'contra', 'K1',
                           'viol_level', 'viol_duration', 'viol_recovery', 'K2', 'K3', 'K4', 'K5', 'max_duration']].round(3).to_dict('records')

    # ---------- рисунок 4.1: розподіл K2 за методами (усі профілі)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    methods = ['CSP', 'Відпал', 'Жадібний', 'Шаблон']
    data = [ok[ok.method == m].K2.values for m in methods]
    bp = ax.boxplot(data, vert=False, widths=0.55, patch_artist=True, showfliers=True,
                    medianprops=dict(color='#0b0b0b', lw=1.6), flierprops=dict(marker='o', ms=3, mfc='none', mec='#52514e'),
                    whiskerprops=dict(color='#52514e'), capprops=dict(color='#52514e'))
    for patch, m in zip(bp['boxes'], methods):
        patch.set(facecolor=COL[m], alpha=0.85, edgecolor='#0b0b0b', hatch=HATCH[m])
    ax.set_yticks(range(1, len(methods) + 1), [LABEL[m] for m in methods])
    for i, d in enumerate(data, 1):
        ax.text(max(np.max(d), 0) + 0.01, i, f'середнє {np.mean(d):.3f}'.replace('.', ','), va='center', fontsize=9, color='#0b0b0b')
    ax.set_xlabel('Відхилення обсягу K₂ (менше — краще)')
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:.1f}'.replace('.', ',')))
    ax.invert_yaxis()
    ax.set_xlim(-0.01, max(np.max(d) for d in data) * 1.35)
    fig.tight_layout(); fig.savefig(FIG / 'k2_box.png', dpi=220); plt.close(fig)

    # ---------- рисунок 4.2: K2 за типом обладнання
    eq = ['зал', 'дім', 'мінімум']
    tab = ok.groupby(['equip', 'method']).K2.mean().unstack().loc[eq, methods]
    wd = 0.8 / len(methods)
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    x = np.arange(len(eq))
    for k, m in enumerate(methods):
        bars = ax.bar(x + (k - (len(methods) - 1) / 2) * wd, tab[m], wd - 0.02, color=COL[m], hatch=HATCH[m], edgecolor='#0b0b0b',
                      lw=0.6, label=LABEL[m])
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.005, f'{b.get_height():.2f}', ha='center',
                    fontsize=8)
    ax.set_xticks(x, ['тренажерний зал', 'домашні умови', 'мінімальне'])
    ax.set_ylabel('Середнє K₂'); ax.legend(frameon=False, fontsize=9, ncols=3, loc='upper left')
    ax.set_ylim(0, tab.values.max() * 1.3)
    fig.tight_layout(); fig.savefig(FIG / 'k2_equip.png', dpi=220); plt.close(fig)

    # ---------- чутливість
    if (RES / 'sensitivity.csv').exists():
        s = pd.read_csv(RES / 'sensitivity.csv')
        base = s[s.config == 'базова'].set_index('profile')
        rows = []
        for c, g in s.groupby('config', sort=False):
            g = g.set_index('profile')
            rows.append(dict(config=c, K2=g.K2.mean(), K3=g.K3.mean(), K4_log=g.K4_log.mean(), K5=g.K5.mean(),
                             n_ex=g.n_exercises.mean(), sets=g.total_sets.mean(),
                             same_K2=float((g.K2.round(6) == base.K2.round(6)).mean()),
                             rt=g.runtime.median()))
        OUT['sensitivity'] = pd.DataFrame(rows).round(4).to_dict('records')

    # ---------- масштабованість
    if (RES / 'scalability.csv').exists():
        sc = pd.read_csv(RES / 'scalability.csv')
        OUT['scalability'] = sc.groupby(['n_ex', 'n_days']).agg(rt=('runtime', 'median'), rt_max=('runtime', 'max'),
                                                                 opt=('status', lambda x: (x == 'optimal').mean()),
                                                                 vars=('n_vars', 'median'), gap=('gap', 'max'),
                                                                 g_rt=('greedy_runtime', 'median'),
                                                                 K2=('K2', 'mean'), gK2=('greedy_K2', 'mean')).round(4).reset_index().to_dict('records')
        fig, ax = plt.subplots(figsize=(6.4, 3.4))
        mk = {3: 'o', 4: 's', 6: '^'}
        cols = {3: '#2a78d6', 4: '#eb6834', 6: '#1baf7a'}
        agg = sc.groupby(['n_days', 'n_ex']).runtime.median().reset_index()
        for nd, g in agg.groupby('n_days'):
            ax.plot(g.n_ex, g.runtime, marker=mk[nd], color=cols[nd], lw=2, ms=7, label=f'{nd} дні' if nd < 5 else f'{nd} днів')
        ga = sc.groupby('n_ex').greedy_runtime.median()
        ax.plot(ga.index, ga.values, ls='--', color='#52514e', lw=1.5, marker='x', label='жадібна евристика')
        ax.axhline(30, color='#d03b3b', lw=1, ls=':'); ax.text(26, 33, 'ліміт 30 с', fontsize=8, color='#52514e')
        ax.set_xscale('log'); ax.set_yscale('log')
        ax.set_xticks([25, 50, 100, 200, 400], ['25', '50', '100', '200', '400'])
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_yticks([0.001, 0.01, 0.1, 1, 10], ['0,001', '0,01', '0,1', '1', '10'])
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.set_xlabel('Кількість допустимих вправ $|E_U|$'); ax.set_ylabel('Медіанний час, с')
        ax.legend(frameon=False, fontsize=9, loc='center right')
        fig.tight_layout(); fig.savefig(FIG / 'scalability.png', dpi=220); plt.close(fig)

    # ---------- адаптація
    ad = pd.read_csv(RES / 'adaptation.csv')
    order = ['rule', 'rule_beta1', 'rule_exact', 'linear', 'fixed']
    agg = ad.groupby('strategy').agg(true_rir=('mean_true_rir', 'mean'), mae=('mae_rir', 'mean'),
                                      zone=('in_zone', 'mean'), fail=('failure_rate', 'mean'),
                                      load_gain=('load_gain', 'mean'), true_gain=('true_gain', 'mean'),
                                      hard=('share_hard', 'mean')).loc[order]
    OUT['adaptation'] = agg.round(4).reset_index().to_dict('records')
    OUT['adaptation_n'] = int(ad.seed.nunique())
    names = {'rule': 'Правило (β=0)', 'rule_beta1': 'Правило (β=1)', 'rule_exact': 'Правило,\nточний RIR',
             'linear': 'Лінійна\nпрогресія', 'fixed': 'Фіксоване\nнавантаження'}
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 3.2))
    c = ['#2a78d6', '#2a78d6', '#2a78d6', '#eb6834', '#1baf7a']
    h = ['', '//', '..', '', '']
    for ax, col, title in [(axs[0], 'fail', 'Частка невдалих підходів'), (axs[1], 'load_gain', 'Приріст робочої ваги за 12 тижнів')]:
        vals = agg[col].values * 100
        bars = ax.barh(range(len(order)), vals, color=c, hatch=h, edgecolor='#0b0b0b', lw=0.6)
        for b, v in zip(bars, vals):
            ax.text(max(v, 0) + vals.max() * 0.02, b.get_y() + b.get_height() / 2, f'{abs(v):.1f} %'.replace('.', ','),
                    va='center', fontsize=8)
        ax.set_yticks(range(len(order)), [names[o] for o in order] if ax is axs[0] else [''] * len(order), fontsize=8)
        ax.invert_yaxis(); ax.set_title(title, fontsize=9); ax.set_xlim(0, vals.max() * 1.3)
        ax.set_xlabel('%'); ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f'{v:g}'.replace('.', ',')))
    fig.tight_layout(); fig.savefig(FIG / 'adaptation.png', dpi=220); plt.close(fig)

    (RES / 'summary.json').write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=float), 'utf-8')
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=float)[:6000])


if __name__ == '__main__':
    main()
