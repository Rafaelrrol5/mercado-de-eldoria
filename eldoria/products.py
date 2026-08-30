PRODUCTS = [
    {
        "slug": "espada-das-chamas-antigas", "name": "Espada das Chamas Antigas",
        "price_cents": 1490, "category": "Armas", "rarity": "Épico", "class_name": "Guerreiro",
        "short_description": "Ataque +35 · Elemento Fogo",
        "description": "Uma lâmina forjada nas antigas câmaras de fogo de Eldoria. Suas runas despertam quando o portador entra em combate.",
        "attributes": [("Ataque", "+35"), ("Elemento", "Fogo")], "image_position": "0% 0%",
        "sales_rank": 96, "created_rank": 3, "offer": True,
    },
    {
        "slug": "armadura-do-guardiao", "name": "Armadura do Guardião",
        "price_cents": 2490, "category": "Armaduras", "rarity": "Lendário", "class_name": "Guerreiro",
        "short_description": "Defesa +50",
        "description": "Proteção cerimonial dos guardiões do reino, reforçada para suportar os golpes das criaturas mais perigosas.",
        "attributes": [("Defesa", "+50"), ("Resistência", "+12")], "image_position": "50% 0%",
        "sales_rank": 82, "created_rank": 2, "offer": False,
    },
    {
        "slug": "amuleto-da-lua", "name": "Amuleto da Lua",
        "price_cents": 990, "category": "Acessórios", "rarity": "Raro", "class_name": "Todas",
        "short_description": "Mana +20 · Sorte +5",
        "description": "Um amuleto que concentra a luz lunar e favorece aventureiros que exploram Eldoria depois do anoitecer.",
        "attributes": [("Mana", "+20"), ("Sorte", "+5")], "image_position": "100% 0%",
        "sales_rank": 88, "created_rank": 4, "offer": False,
    },
    {
        "slug": "pacote-inicial-do-aventureiro", "name": "Pacote Inicial do Aventureiro",
        "price_cents": 2990, "category": "Pacotes", "rarity": "Raro", "class_name": "Todas",
        "short_description": "5 itens essenciais para começar",
        "description": "Uma seleção equilibrada de suprimentos, moedas e equipamentos para iniciar sua jornada com mais segurança.",
        "attributes": [("Conteúdo", "5 itens"), ("Bônus", "1.000 moedas")], "image_position": "0% 100%",
        "sales_rank": 100, "created_rank": 1, "offer": True,
    },
    {
        "slug": "pocao-do-crepusculo", "name": "Poção do Crepúsculo",
        "price_cents": 590, "category": "Poções", "rarity": "Comum", "class_name": "Todas",
        "short_description": "Recupera 80 pontos de vida",
        "description": "Preparada por alquimistas da fronteira, restaura forças durante expedições e combates prolongados.",
        "attributes": [("Cura", "+80 HP"), ("Uso", "Consumível")], "image_position": "50% 100%",
        "sales_rank": 75, "created_rank": 5, "offer": False,
    },
    {
        "slug": "manto-do-explorador", "name": "Manto do Explorador",
        "price_cents": 1190, "category": "Cosméticos", "rarity": "Épico", "class_name": "Todas",
        "short_description": "Visual exclusivo de explorador",
        "description": "Um manto elegante inspirado nos cartógrafos que atravessaram os vales mais remotos do reino.",
        "attributes": [("Tipo", "Visual"), ("Vínculo", "Conta")], "image_position": "100% 100%",
        "sales_rank": 68, "created_rank": 6, "offer": False,
    },
]

CATEGORIES = ["Todas", "Armas", "Armaduras", "Poções", "Acessórios", "Cosméticos", "Pacotes", "Ofertas"]
RARITIES = ["Todas", "Comum", "Raro", "Épico", "Lendário"]
CLASSES = ["Todas", "Guerreiro"]


def get_product(slug):
    return next((product for product in PRODUCTS if product["slug"] == slug), None)


def format_brl(price_cents):
    value = f"{price_cents / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {value}"

