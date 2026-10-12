"""Estilo dos gráficos, igual nos dois notebooks."""
import matplotlib.pyplot as plt
import seaborn as sns

from src import config

AZUL, LARANJA, VERDE, CINZA, TEXTO = '#2a78d6', '#eb6834', '#1baf7a', '#898781', '#52514e'
FIGURAS = config.RESULTADOS / 'figuras'


def configurar():
    FIGURAS.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style='whitegrid', rc={
        'figure.dpi': 110, 'savefig.dpi': 160, 'savefig.bbox': 'tight', 'figure.facecolor': 'white',
        'axes.spines.top': False, 'axes.spines.right': False, 'axes.edgecolor': '#c3c2b7',
        'grid.color': '#e1e0d9', 'grid.linewidth': 0.6, 'axes.titlesize': 11, 'axes.titleweight': 'bold',
        'axes.titlelocation': 'left', 'axes.labelsize': 9, 'xtick.labelsize': 8.5, 'ytick.labelsize': 8.5,
        'axes.labelcolor': TEXTO, 'xtick.color': TEXTO, 'ytick.color': TEXTO})


def salvar(fig, nome):
    """Grava a figura em reports/figuras e mostra no notebook."""
    fig.savefig(FIGURAS / nome)
    plt.show()


def rotular(ax, barras, **kwargs):
    ax.bar_label(barras, padding=3, fontsize=8.5, color=TEXTO, **kwargs)


def limpar_eixos(ax, eixo='x'):
    """Tira a grade e os números do eixo de valores quando as barras já têm rótulo."""
    ax.grid(visible=False)
    ax.tick_params(length=0)
    (ax.set_xticks if eixo == 'x' else ax.set_yticks)([])
