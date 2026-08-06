import './globals.css';
export const metadata = { title: 'Mapa de Produtividade', description: 'Processamento de mapas de colheita' };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
