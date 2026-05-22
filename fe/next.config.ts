import createBundleAnalyzer from '@next/bundle-analyzer';

const withAnalyzer = createBundleAnalyzer({ enabled: process.env.ANALYZE === 'true' });

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  compiler: {
    removeConsole: process.env.NODE_ENV === 'production',
  },
  experimental: {
    optimizePackageImports: ['recharts', 'lucide-react'],
  },
};

export default withAnalyzer(nextConfig);