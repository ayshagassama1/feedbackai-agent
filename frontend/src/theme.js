/**
 * Thème partagé : tokens extraits du repo oryel-website (config Tailwind + index.css),
 * étape 5.2. Les couleurs de marque (teal) et neutres (gray) sont les valeurs exactes de la
 * palette Tailwind utilisée sur oryel.dev. Le rouge est le --destructive déjà présent dans sa
 * palette. L'ambre est le seul ajout non issu d'oryel.dev, retenu avec Aissatou pour couvrir
 * les états intermédiaires (priorité moyenne, sentiment neutre) que sa palette ne couvre pas.
 */

export const theme = {
  font: {
    sans: "'Inter Variable', 'Inter', system-ui, sans-serif",
  },

  radius: {
    sm: 6,
    md: 8,
    lg: 10,
    pill: 999,
  },

  // Élévation au repos (shadow-sm) et au survol (shadow-lg teinté teal), valeurs oryel.dev
  // (voir ServicesSection.jsx : "shadow-sm hover:shadow-lg", HeroSection.jsx :
  // "hover:shadow-lg hover:shadow-teal-100 hover:-translate-y-0.5").
  shadow: {
    sm: "0 1px 2px 0 rgba(17, 24, 39, 0.05)",
    md: "0 4px 6px -1px rgba(17, 24, 39, 0.08), 0 2px 4px -2px rgba(17, 24, 39, 0.06)",
    lg: "0 10px 15px -3px rgba(13, 148, 136, 0.18), 0 4px 6px -4px rgba(13, 148, 136, 0.12)",
  },

  color: {
    // Texte
    textPrimary:   "#111827", // gray-900
    textSecondary: "#4B5563", // gray-600
    textTertiary:  "#6B7280", // gray-500
    textOnBrand:   "#FFFFFF",

    // Fond
    bgPrimary:   "#FFFFFF",
    bgSecondary: "#F9FAFB", // gray-50
    bgTertiary:  "#F3F4F6", // gray-100

    // Bordures
    borderPrimary:   "#D1D5DB", // gray-300
    borderSecondary: "#E5E7EB", // gray-200
    borderTertiary:  "#F3F4F6", // gray-100

    // Marque (teal, identité oryel.dev)
    brand:        "#0D9488", // teal-600
    brandHover:   "#0F766E", // teal-700
    brandLight:   "#F0FDFA", // teal-50
    brandBorder:  "#CCFBF1", // teal-100

    // Négatif / priorité haute / erreur (rouge, déjà dans la palette oryel.dev)
    danger:       "#B91C1C", // red-700
    dangerBg:     "#FEF2F2", // red-50
    dangerBorder: "#FECACA", // red-200

    // Intermédiaire / priorité moyenne / sentiment neutre (ambre, seul ajout hors oryel.dev)
    warning:       "#B45309", // amber-700
    warningBg:     "#FFFBEB", // amber-50
    warningBorder: "#FDE68A", // amber-200
  },
};

/** Résout une couleur de sentiment (-1..1) sur les trois teintes du thème. */
export function sentimentColor(sentiment) {
  if (sentiment > 0.2) return theme.color.brand;
  if (sentiment < -0.2) return theme.color.danger;
  return theme.color.warning;
}

/** Résout label + couleurs pour une priorité (high/medium/low). */
export function priorityStyle(priority, lang = "fr") {
  const labels = {
    fr: { high: "Haute", medium: "Moyenne", low: "Basse" },
    en: { high: "High", medium: "Medium", low: "Low" },
  };
  const styles = {
    high:   { color: theme.color.danger,  bg: theme.color.dangerBg,  border: theme.color.dangerBorder },
    medium: { color: theme.color.warning, bg: theme.color.warningBg, border: theme.color.warningBorder },
    low:    { color: theme.color.textTertiary, bg: theme.color.bgTertiary, border: theme.color.borderSecondary },
  };
  return { label: labels[lang][priority] ?? priority, ...(styles[priority] ?? styles.low) };
}
